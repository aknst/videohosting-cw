import uuid

from sqlmodel import Field, SQLModel


class CategoryBase(SQLModel):
    name: str = Field(..., min_length=1, max_length=50)


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)


class CategoryPublic(CategoryBase):
    id: uuid.UUID

    model_config = {"from_attributes": True}


class CategoriesPublic(SQLModel):
    data: list[CategoryPublic]
    count: int
