import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional

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
    avatar_url: str | None = Field(default=None, max_length=255)
    bio: str | None = Field(default=None, max_length=500)
    hashed_password: str = Field(...)

    items: list["Item"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
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

    playlists: list["Playlist"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    views: list["VideoView"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    likes: list["VideoLike"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    comments: list["Comment"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    complaints: list["Complaint"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class Item(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


class Video(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    filename: str = Field(max_length=255)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="videos")

    is_processed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    tags: list["VideoTagLink"] = Relationship(
        back_populates="video",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    views: list["VideoView"] = Relationship(
        back_populates="video",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    likes: list["VideoLike"] = Relationship(
        back_populates="video",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    comments: list["Comment"] = Relationship(
        back_populates="video",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    complaints: list["Complaint"] = Relationship(
        back_populates="video",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    playlists: list["PlaylistVideoLink"] = Relationship(
        back_populates="video",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class Playlist(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    owner: User | None = Relationship(back_populates="playlists")
    videos: list["PlaylistVideoLink"] = Relationship(
        back_populates="playlist",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class PlaylistVideoLink(SQLModel, table=True):
    playlist_id: uuid.UUID = Field(
        foreign_key="playlist.id",
        primary_key=True,
    )
    video_id: uuid.UUID = Field(
        foreign_key="video.id",
        primary_key=True,
    )
    order: int = Field(default=0)

    playlist: Playlist = Relationship(back_populates="videos")
    video: Video = Relationship(back_populates="playlists")


class Tag(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(min_length=1, max_length=50, unique=True)
    videos: list["VideoTagLink"] = Relationship(
        back_populates="tag",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class VideoTagLink(SQLModel, table=True):
    video_id: uuid.UUID = Field(
        foreign_key="video.id",
        primary_key=True,
    )
    tag_id: uuid.UUID = Field(
        foreign_key="tag.id",
        primary_key=True,
    )

    video: Video = Relationship(back_populates="tags")
    tag: Tag = Relationship(back_populates="videos")


class VideoLike(SQLModel, table=True):
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        primary_key=True,
    )
    video_id: uuid.UUID = Field(
        foreign_key="video.id",
        primary_key=True,
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    viewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    user: User = Relationship(back_populates="views")
    video: Video = Relationship(back_populates="views")


class Comment(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False)
    video_id: uuid.UUID = Field(foreign_key="video.id", nullable=False)
    parent_id: uuid.UUID | None = Field(foreign_key="comment.id", default=None)
    content: str = Field(min_length=1, max_length=1000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    user: User = Relationship(back_populates="comments")
    video: Video = Relationship(back_populates="comments")

    # Родительский комментарий (many-to-one)
    parent: Optional["Comment"] = Relationship(
        back_populates="replies", sa_relationship_kwargs={"remote_side": "Comment.id"}
    )

    # Ответы на комментарий (one-to-many)
    replies: list["Comment"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class Complaint(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False)
    video_id: uuid.UUID = Field(foreign_key="video.id", nullable=False)
    reason: str = Field(min_length=1, max_length=255)
    details: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    user: User = Relationship(back_populates="complaints")
    video: Video = Relationship(back_populates="complaints")
