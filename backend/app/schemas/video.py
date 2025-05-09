import uuid
from sqlmodel import Field, SQLModel


class VideoBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


class VideoCreate(VideoBase):
    pass


class VideoUpdate(VideoBase):
    title: str | None = Field(default=None, min_length=1, max_length=255)


class VideoPublic(VideoBase):
    id: uuid.UUID
    filename: str
    is_processed: bool
    owner_id: uuid.UUID


class VideosPublic(SQLModel):
    data: list[VideoPublic]
    count: int
