import uuid
from typing import Any

from sqlmodel import Session, asc, desc, func, or_, select

from app.core.security import get_password_hash, verify_password
from app.models import Category, User, Video, VideoLike, VideoView
from app.schemas import UserCreate, UserUpdate, VideoCreate
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.schemas.video import VideoUpdate


class UserCrud:
    def create_user(self, *, session: Session, user_create: UserCreate) -> User:
        """
        Создает нового пользователя, хэшируя пароль.
        """
        db_obj = User.model_validate(
            user_create,
            update={"hashed_password": get_password_hash(user_create.password)},
        )
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def update_user(
        self, *, session: Session, db_user: User, user_in: UserUpdate
    ) -> User:
        """
        Обновляет данные пользователя. Если передан новый пароль, то он хэшируется.
        """
        user_data = user_in.model_dump(exclude_unset=True)
        extra_data: dict[str, Any] = {}

        if "password" in user_data:
            # хэшируем новый пароль
            extra_data["hashed_password"] = get_password_hash(user_data.pop("password"))

        # применяем обновления к модели
        db_user.sqlmodel_update(user_data, update=extra_data)
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
        return db_user

    def get_user_by_email(self, *, session: Session, email: str) -> Any:
        """
        Получает пользователя по email или возвращает None, если не найден.
        """
        stmt = select(User).where(User.email == email)
        return session.exec(stmt).first()

    def authenticate(self, *, session: Session, email: str, password: str) -> Any:
        """
        Проверяет, существует ли пользователь с таким email, и совпадает ли пароль.
        """
        user = self.get_user_by_email(session=session, email=email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user


class VideoCrud:
    def create_video(
        self, *, session: Session, video_in: VideoCreate, owner_id: uuid.UUID
    ) -> Video:
        """
        Создает новое видео.
        """
        video = Video(
            id=uuid.uuid4(),
            title=video_in.title,
            description=video_in.description,
            owner_id=owner_id,
            filename=video_in.filename,
            category_id=video_in.category_id,
            is_private=video_in.is_private,
            thumbnail_filename=video_in.thumbnail_file,
        )
        session.add(video)
        session.commit()
        session.refresh(video)

        return video

    def update_video(
        self,
        *,
        session: Session,
        video_id: uuid.UUID,
        video_in: VideoUpdate,
    ) -> Video:
        """
        Обновляет метаданные видео.
        """
        video = session.get(Video, video_id)
        if video:
            if video_in.title is not None:
                video.title = video_in.title
            if video_in.description is not None:
                video.description = video_in.description
            if video_in.category_id is not None:
                video.category_id = video_in.category_id

            session.add(video)
            session.commit()
            session.refresh(video)

        return video

    def get_video(self, *, session: Session, video_id: uuid.UUID) -> Video | None:
        """
        Возвращает видео по его ID или None.
        """
        return session.get(Video, video_id)

    def get_videos(
        self,
        *,
        session: Session,
        skip: int,
        limit: int,
        sort_desc: bool,
        category_id: uuid.UUID | None,
        search: str | None,
        viewer_id: uuid.UUID | None,
    ) -> tuple[list[Video], int]:
        """
        Возвращает (видео, общее количество), применяя:
         - фильтр по категориям
         - поиск подстрок по названию/описанию без учета регистра
         - если задан viewer_id: только видео, за owner_id которых следует viewer_id
         - упорядочение по значению created_at desc (новый) или asc (старый)
         - разбивка на страницы с помощью пропуска/ограничения
        """
        stmt = select(Video)

        if category_id:
            stmt = stmt.where(Video.category_id == category_id)

        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Video.title.ilike(pattern),
                    Video.description.ilike(pattern),
                )
            )

        if viewer_id:
            from .models import UserFollowerLink  # adjust import

            stmt = stmt.join(
                UserFollowerLink, Video.owner_id == UserFollowerLink.user_id
            ).where(UserFollowerLink.follower_id == viewer_id)

        count = session.exec(select(func.count()).select_from(stmt.subquery())).one()

        order = desc(Video.created_at) if sort_desc else asc(Video.created_at)
        stmt = stmt.order_by(order)

        stmt = stmt.offset(skip).limit(limit)

        videos = session.exec(stmt).all()
        return videos, count

    def delete_video(self, *, session: Session, video_id: uuid.UUID) -> None:
        """
        Удаляет видео по ID, если оно существует.
        """
        video = session.get(Video, video_id)
        if video:
            session.delete(video)
            session.commit()

    def like_video(
        self, *, session: Session, user_id: uuid.UUID, video_id: uuid.UUID
    ) -> None:
        """
        Ставит лайк от пользователя, если он еще не был поставлен.
        """
        exists = session.exec(
            select(VideoLike).where(
                VideoLike.user_id == user_id, VideoLike.video_id == video_id
            )
        ).first()
        if not exists:
            like = VideoLike(user_id=user_id, video_id=video_id)
            session.add(like)
            session.commit()

    def unlike_video(
        self, *, session: Session, user_id: uuid.UUID, video_id: uuid.UUID
    ) -> None:
        """
        Снимает лайк пользователя, если он был поставлен.
        """
        like = session.exec(
            select(VideoLike).where(
                VideoLike.user_id == user_id, VideoLike.video_id == video_id
            )
        ).first()
        if like:
            session.delete(like)
            session.commit()

    def view_video(
        self, *, session: Session, user_id: uuid.UUID, video_id: uuid.UUID
    ) -> None:
        """
        Регистрирует просмотр видео пользователем (или анонимом при user_id=None).
        """
        view = VideoView(user_id=user_id, video_id=video_id)
        session.add(view)
        session.commit()


class CategoryCrud:
    def get(self, *, session: Session, id: uuid.UUID) -> Any:
        """
        Возвращает категорию по её ID или None.
        """
        return session.get(Category, id)

    def get_by_name(self, *, session: Session, name: str) -> Any:
        """
        Возвращает категорию по её имени или None.
        """
        statement = select(Category).where(Category.name == name)
        return session.exec(statement).first()

    def get_categories(
        self, *, session: Session, skip: int = 0, limit: int = 100
    ) -> tuple[list[Category], int]:
        """
        Пагинация списка категорий: возвращает кортеж (список, общее количество).
        """
        total = session.exec(select(func.count()).select_from(Category)).one()
        categories = session.exec(select(Category).offset(skip).limit(limit)).all()
        return categories, total

    def create(self, *, session: Session, obj_in: CategoryCreate) -> Category:
        """
        Создаёт новую категорию.
        """
        category = Category(id=uuid.uuid4(), name=obj_in.name)
        session.add(category)
        session.commit()
        session.refresh(category)
        return category

    def update(
        self, *, session: Session, db_obj: Category, obj_in: CategoryUpdate
    ) -> Category:
        """
        Обновляет существующую категорию.
        """
        if obj_in.name is not None:
            db_obj.name = obj_in.name
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def remove(self, *, session: Session, id: uuid.UUID) -> None:
        """
        Удаляет категорию по ID, если она существует.
        """
        category = session.get(Category, id)
        if category:
            session.delete(category)
            session.commit()


category_crud = CategoryCrud()
user_crud = UserCrud()
video_crud = VideoCrud()
