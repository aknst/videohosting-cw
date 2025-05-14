import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from pydantic import EmailStr
from sqlmodel import Field, Relationship, SQLModel


class UserRole(str, PyEnum):
    USER = "USER"
    MODERATOR = "MODERATOR"
    ADMIN = "ADMIN"


class UserFollowerLink(SQLModel, table=True):
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        primary_key=True,
    )
    follower_id: uuid.UUID = Field(
        foreign_key="user.id",
        primary_key=True,
    )


class User(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    full_name: str | None = Field(default=None, max_length=255)
    role: UserRole = Field(default=UserRole.USER, nullable=False)
    bio: str | None = Field(default=None, max_length=500)
    hashed_password: str = Field(...)

    videos: list["Video"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    followers: list["User"] = Relationship(
        back_populates="following",
        link_model=UserFollowerLink,
        sa_relationship_kwargs={
            "primaryjoin": "User.id==UserFollowerLink.user_id",
            "secondaryjoin": "User.id==UserFollowerLink.follower_id",
        },
    )
    following: list["User"] = Relationship(
        back_populates="followers",
        link_model=UserFollowerLink,
        sa_relationship_kwargs={
            "primaryjoin": "User.id==UserFollowerLink.follower_id",
            "secondaryjoin": "User.id==UserFollowerLink.user_id",
        },
    )
    views: list["VideoView"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    likes: list["VideoLike"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class Category(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(min_length=1, max_length=50, unique=True)

    videos: list["Video"] = Relationship(back_populates="category")


class Video(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    filename: str = Field(max_length=255)

    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="videos")

    category_id: uuid.UUID = Field(foreign_key="category.id", nullable=True)
    category: Category | None = Relationship(back_populates="videos")

    is_private: bool = Field(default=False)
    thumbnail_filename: str | None = Field(default=None, max_length=255)

    is_processed: bool = Field(default=False)
    created_at: datetime = Field(default=datetime.now(timezone.utc), nullable=False)
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )

    views: list["VideoView"] = Relationship(
        back_populates="video",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    likes: list["VideoLike"] = Relationship(
        back_populates="video",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class VideoLike(SQLModel, table=True):
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        primary_key=True,
    )
    video_id: uuid.UUID = Field(
        foreign_key="video.id",
        primary_key=True,
    )
    created_at: datetime = Field(default=datetime.now(timezone.utc), nullable=False)

    user: User = Relationship(back_populates="likes")
    video: Video = Relationship(back_populates="likes")


class VideoView(SQLModel, table=True):
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        primary_key=True,
    )
    video_id: uuid.UUID = Field(
        foreign_key="video.id",
        primary_key=True,
    )
    viewed_at: datetime = Field(default=datetime.now(timezone.utc), nullable=False)

    user: User = Relationship(back_populates="views")
    video: Video = Relationship(back_populates="views")
