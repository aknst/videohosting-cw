from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.core.config import settings


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


tags_metadata = [
    {
        "name": "login",
        "description": """
Авторизация и восстановление доступа пользователей.
Здесь реализована логика входа в систему по протоколу OAuth2 с выдачей JWT-токена, проверка работоспособности токена, восстановление пароля по email и его последующая смена.
Также доступен эндпоинт для просмотра HTML-содержимого email-сообщения восстановления пароля.
""",
    }
]

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    openapi_tags=tags_metadata,
)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)
