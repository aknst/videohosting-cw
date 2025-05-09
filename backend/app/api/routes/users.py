import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import col, delete, func, select

from app import crud
from app.api.deps import (
    CurrentUser,
    SessionDep,
    get_current_active_superuser,
    required_role,
)
from app.core.config import settings
from app.models import Item, User, UserFollowerLink, UserRole
from app.schemas import (
    Message,
    UserCreate,
    UserPublic,
    UserRegister,
    UsersPublic,
    UserUpdate,
)
from app.utils import generate_new_account_email, send_email

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/",
    dependencies=[Depends(required_role(UserRole.MODERATOR))],
    response_model=UsersPublic,
)
def read_users(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    """
    Retrieve users.
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
    Create new user.
    """
    user = crud.get_user_by_email(session=session, email=user_in.email)  # noqa: F821
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )

    user = user.create_user(session=session, user_create=user_in)
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
    Create new user without the need to be logged in.
    """
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system",
        )
    user_create = UserCreate.model_validate(user_in)
    user = user.create_user(session=session, user_create=user_create)
    return user


@router.get("/{user_id}", response_model=UserPublic)
def read_user_by_id(
    user_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Any:
    """
    Get a specific user by id.
    """
    user = session.get(User, user_id)
    if user == current_user:
        return user
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="The user doesn't have enough privileges",
        )
    return user


@router.patch(
    "/{user_id}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UserPublic,
)
def update_user(
    *,
    session: SessionDep,
    user_id: uuid.UUID,
    user_in: UserUpdate,
) -> Any:
    """
    Update a user.
    """

    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="The user with this id does not exist in the system",
        )
    if user_in.email:
        existing_user = crud.get_user_by_email(session=session, email=user_in.email)
        if existing_user and existing_user.id != user_id:
            raise HTTPException(
                status_code=409, detail="User with this email already exists"
            )

    db_user = crud.update_user(session=session, db_user=db_user, user_in=user_in)
    return db_user


@router.delete("/{user_id}", dependencies=[Depends(get_current_active_superuser)])
def delete_user(
    session: SessionDep, current_user: CurrentUser, user_id: uuid.UUID
) -> Message:
    """
    Delete a user.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user == current_user:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    statement = delete(Item).where(col(Item.owner_id) == user_id)
    session.exec(statement)  # type: ignore
    session.delete(user)
    session.commit()
    return Message(message="User deleted successfully")


@router.post("/{user_id}/follow", response_model=Message)
def follow_user(
    user_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Any:
    """Подписаться на пользователя"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя подписаться на самого себя")
    target = session.get(User, user_id)
    if not target or (user_id != current_user.id and not current_user.is_superuser):
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    # check existing
    existing = session.exec(
        select(UserFollowerLink)
        .where(UserFollowerLink.user_id == user_id)
        .where(UserFollowerLink.follower_id == current_user.id)
    ).first()
    if existing:
        return Message(message="Уже подписаны")
    link = UserFollowerLink(user_id=user_id, follower_id=current_user.id)
    session.add(link)
    session.commit()
    return Message(message="Подписка оформлена")


@router.delete("/{user_id}/follow", response_model=Message)
def unfollow_user(
    user_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Any:
    """Отписаться от пользователя"""
    stmt = delete(UserFollowerLink).where(
        UserFollowerLink.user_id == user_id,
        UserFollowerLink.follower_id == current_user.id,
    )
    result = session.exec(stmt)
    session.commit()
    if result.rowcount == 0:
        raise HTTPException(
            status_code=400, detail="Не подписаны на этого пользователя"
        )
    return Message(message="Отписка оформлена")


@router.get("/{user_id}/followers", response_model=UsersPublic)
def get_followers(
    user_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """Список подписчиков пользователя"""
    target = session.get(User, user_id)
    if not target or (user_id != current_user.id and not current_user.is_superuser):
        raise HTTPException(
            status_code=404, detail="Пользователь не найден или приватный"
        )
    total = session.exec(
        select(func.count())
        .select_from(UserFollowerLink)
        .where(UserFollowerLink.user_id == user_id)
    ).one()
    stmt = (
        select(User)
        .join(UserFollowerLink, User.id == UserFollowerLink.follower_id)
        .where(UserFollowerLink.user_id == user_id)
        .offset(skip)
        .limit(limit)
    )
    users = session.exec(stmt).all()
    return UsersPublic(data=users, count=total)


@router.get("/{user_id}/following", response_model=UsersPublic)
def get_following(
    user_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """Список подписок пользователя"""
    target = session.get(User, user_id)
    if not target or (user_id != current_user.id and not current_user.is_superuser):
        raise HTTPException(
            status_code=404, detail="Пользователь не найден или приватный"
        )
    total = session.exec(
        select(func.count())
        .select_from(UserFollowerLink)
        .where(UserFollowerLink.follower_id == user_id)
    ).one()
    stmt = (
        select(User)
        .join(UserFollowerLink, User.id == UserFollowerLink.user_id)
        .where(UserFollowerLink.follower_id == user_id)
        .offset(skip)
        .limit(limit)
    )
    users = session.exec(stmt).all()
    return UsersPublic(data=users, count=total)
