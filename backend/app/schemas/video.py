import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models import Category


class VideoOwnerPublic(SQLModel):
    id: uuid.UUID
    full_name: str | None


class VideoBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    category_id: uuid.UUID | None = Field(default=None, foreign_key="category.id")


class VideoCreate(VideoBase):
    filename: str = Field(max_length=255)
    thumbnail_file: str | None = None
    is_private: bool = False


class VideoUpdate(VideoBase):
    pass


class VideoPublic(SQLModel):
    id: uuid.UUID
    title: str
    description: str | None
    is_private: bool
    owner: VideoOwnerPublic | None
    category: Category | None
    created_at: datetime
    updated_at: datetime


class VideosPublic(SQLModel):
    data: list[VideoPublic]
    count: int


class VideoStats(SQLModel):
    views: int
    likes: int
