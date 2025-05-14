from fastapi import APIRouter

from app.api.routes import categories, login, me, private, users, utils, videos
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(me.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(videos.router)
api_router.include_router(categories.router)

if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
