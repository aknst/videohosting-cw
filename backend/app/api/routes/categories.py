import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import SessionDep, required_role
from app.crud import category_crud
from app.models import UserRole
from app.schemas import Message
from app.schemas.category import (
    CategoriesPublic,
    CategoryCreate,
    CategoryPublic,
    CategoryUpdate,
)

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get(
    "/",
    response_model=CategoriesPublic,
)
async def read_categories(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Получить список категорий.
    """
    cats, total = category_crud.get_categories(session=session, skip=skip, limit=limit)

    return CategoriesPublic(data=cats, count=total)


@router.post(
    "/",
    response_model=CategoryPublic,
    dependencies=[Depends(required_role(UserRole.ADMIN))],
)
async def create_category(
    *,
    session: SessionDep,
    category_in: CategoryCreate,
) -> Any:
    """
    Создать новую категорию. Только для администраторов.
    """
    existing = category_crud.get_by_name(session=session, name=category_in.name)
    if existing:
        raise HTTPException(
            status_code=400,
            detail="A category with that name already exists",
        )
    category = category_crud.create(session=session, obj_in=category_in)
    return category


@router.put(
    "/{id}",
    response_model=CategoryPublic,
    dependencies=[Depends(required_role(UserRole.ADMIN))],
)
async def update_category(
    *,
    session: SessionDep,
    id: uuid.UUID,
    category_in: CategoryUpdate,
) -> Any:
    """
    Обновить существующую категорию. Только для администраторов.
    """
    category = category_crud.get(session=session, id=id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    if category_in.name and category_in.name != category.name:
        conflict = category_crud.get_by_name(session=session, name=category_in.name)
        if conflict:
            raise HTTPException(
                status_code=400,
                detail="A category with that name already exists",
            )
    updated = category_crud.update(session=session, db_obj=category, obj_in=category_in)
    return updated


@router.delete(
    "/{id}",
    response_model=Message,
    dependencies=[Depends(required_role(UserRole.ADMIN))],
)
async def delete_category(
    *,
    session: SessionDep,
    id: uuid.UUID,
) -> Any:
    """
    Удалить категорию. Только для администраторов.
    """
    category = category_crud.get(session=session, id=id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    category_crud.remove(session=session, id=id)
    return Message(message="Категория успешно удалена.")
