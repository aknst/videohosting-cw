import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import func, select

from app.api.deps import (
    CurrentUser,
    SessionDep,
    get_current_active_superuser,
    required_role,
)
from app.core.config import settings
from app.crud import user_crud
from app.models import User, UserFollowerLink, UserRole, Video, VideoView
from app.schemas import (
    Message,
    UserCreate,
    UserPublic,
    UserRegister,
    UsersPublic,
    UserUpdate,
)
from app.schemas.video import VideosPublic
from app.utils import generate_new_account_email, send_email

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/",
    dependencies=[Depends(required_role(UserRole.MODERATOR))],
    response_model=UsersPublic,
)
def read_users(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    """
    Получение списка пользователей.
    """

    count_statement = select(func.count()).select_from(User)
    count = session.exec(count_statement).one()

    statement = select(User).offset(skip).limit(limit)
    users = session.exec(statement).all()

    return UsersPublic(data=users, count=count)


@router.post(
    "/", dependencies=[Depends(get_current_active_superuser)], response_model=UserPublic
)
def create_user(*, session: SessionDep, user_in: UserCreate) -> Any:
    """
    Создание нового пользователя.
    """
    user = user_crud.get_user_by_email(session=session, email=user_in.email)  # noqa: F821
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )

    user = user_crud.create_user(session=session, user_create=user_in)
    if settings.emails_enabled and user_in.email:
        email_data = generate_new_account_email(
            email_to=user_in.email, username=user_in.email, password=user_in.password
        )
        send_email(
            email_to=user_in.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
        )
    return user


@router.post("/signup", response_model=UserPublic)
def register_user(session: SessionDep, user_in: UserRegister) -> Any:
    """
    Регистрация нового пользователя.
    """
    user = user_crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system",
        )
    user_create = UserCreate.model_validate(user_in)
    user = user_crud.create_user(session=session, user_create=user_create)
    return user


@router.get("/{id}", response_model=UserPublic)
def read_user_by_id(
    id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Any:
    """
    Получение пользователя по ID.
    """
    user = session.get(User, id)
    if user == current_user:
        return user
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="The user doesn't have enough privileges",
        )
    return user


@router.patch(
    "/{id}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UserPublic,
)
def update_user(
    *,
    session: SessionDep,
    id: uuid.UUID,
    user_in: UserUpdate,
) -> Any:
    """
    Update a user.
    """

    db_user = session.get(User, id)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="The user with this id does not exist in the system",
        )
    if user_in.email:
        existing_user = user_crud.get_user_by_email(
            session=session, email=user_in.email
        )
        if existing_user and existing_user.id != id:
            raise HTTPException(
                status_code=409, detail="User with this email already exists"
            )

    db_user = user_crud.update_user(session=session, db_user=db_user, user_in=user_in)
    return db_user


@router.delete("/{id}", dependencies=[Depends(get_current_active_superuser)])
def delete_user(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Message:
    """
    Delete a user.
    """
    user = session.get(User, id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user == current_user:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    session.delete(user)
    session.commit()
    return Message(message="User deleted successfully")


@router.post("/{id}/follow", response_model=Message)
def toggle_follow(
    id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Message:
    """
    Toggle subscription to user <id>:
    - If not already following → follow
    - If already following → unfollow
    """
    if id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't subscribe to yourself")

    target = session.get(User, id)
    if not target:
        raise HTTPException(status_code=404, detail="The user was not found")

    # 3. Check for existing link
    existing = session.exec(
        select(UserFollowerLink)
        .where(UserFollowerLink.user_id == id)
        .where(UserFollowerLink.follower_id == current_user.id)
    ).first()

    if existing:
        session.delete(existing)
        session.commit()
        return Message(message="Unsubscribed successfully")

    link = UserFollowerLink(user_id=id, follower_id=current_user.id)
    session.add(link)
    session.commit()
    return Message(message="Subscribed successfully")


@router.get("/{id}/followers", response_model=UsersPublic)
def get_followers(
    id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """Список подписчиков пользователя"""
    target = session.get(User, id)
    if not target or (id != current_user.id and not current_user.is_superuser):
        raise HTTPException(status_code=404, detail="User not found")
    total = session.exec(
        select(func.count())
        .select_from(UserFollowerLink)
        .where(UserFollowerLink.user_id == id)
    ).one()
    stmt = (
        select(User)
        .join(UserFollowerLink, User.id == UserFollowerLink.follower_id)
        .where(UserFollowerLink.user_id == id)
        .offset(skip)
        .limit(limit)
    )
    users = session.exec(stmt).all()
    return UsersPublic(data=users, count=total)


@router.get("/{id}/following", response_model=UsersPublic)
def get_following(
    id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """Список подписок пользователя"""
    target = session.get(User, id)
    if not target or (id != current_user.id and not current_user.is_superuser):
        raise HTTPException(status_code=404, detail="User not found")
    total = session.exec(
        select(func.count())
        .select_from(UserFollowerLink)
        .where(UserFollowerLink.follower_id == id)
    ).one()
    stmt = (
        select(User)
        .join(UserFollowerLink, User.id == UserFollowerLink.user_id)
        .where(UserFollowerLink.follower_id == id)
        .offset(skip)
        .limit(limit)
    )
    users = session.exec(stmt).all()
    return UsersPublic(data=users, count=total)


@router.get("/{id}/view-history", response_model=VideosPublic)
def get_user_view_history(
    id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Список видео, которые пользователь <id> просмотрел
    """
    # проверяем, что пользователь существует (и что либо сам запрашивает, либо суперюзер)
    target = session.get(User, id)
    if not target or (id != current_user.id and not current_user.is_superuser):
        raise HTTPException(status_code=404, detail="User not found")

    # общее число просмотренных видео
    total = session.exec(
        select(func.count()).select_from(VideoView).where(VideoView.user_id == id)
    ).one()

    # сами видео
    stmt = (
        select(Video)
        .join(VideoView, Video.id == VideoView.video_id)
        .where(VideoView.user_id == id)
        .offset(skip)
        .limit(limit)
    )
    videos = session.exec(stmt).all()
    return VideosPublic(data=videos, count=total)
