import os
import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.params import Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlmodel import func, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.crud import video_crud
from app.models import UserRole, VideoLike, VideoView
from app.schemas import Message, VideoCreate, VideoPublic, VideosPublic
from app.schemas.video import VideoStats, VideoUpdate
from app.tasks.video import process_video

UPLOAD_DIR = settings.UPLOAD_DIR
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/videos", tags=["videos"])

CHUNK_SIZE = 1024 * 1024  # 1 MB


@router.post("/", response_model=VideoPublic)
async def upload_video(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    title: str,
    description: str | None = None,
    category_id: uuid.UUID | None = None,
    is_private: bool = False,
    file: UploadFile = File(...),
    thumbnail_file: UploadFile | None = File(None),
) -> Any:
    """
    Загрузить видео
    """
    if not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Invalid video file")

    file_ext = os.path.splitext(file.filename)[-1]
    video_id = uuid.uuid4()
    filename = f"{video_id}{file_ext}"
    filepath = UPLOAD_DIR / filename

    with open(filepath, "wb") as buffer:
        content = await file.read()
        buffer.write(content)

    thumbnail_filename: str | None = None
    if thumbnail_file:
        if not thumbnail_file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Invalid thumbnail file")

        thumbnail_ext = os.path.splitext(thumbnail_file.filename)[-1]
        thumbnail_filename = f"{video_id}_thumbnail{thumbnail_ext}"
        thumbnail_path = UPLOAD_DIR / thumbnail_filename

        with open(thumbnail_path, "wb") as buffer:
            thumb_content = await thumbnail_file.read()
            buffer.write(thumb_content)

    video_in = VideoCreate(
        title=title,
        description=description,
        filename=filename,
        thumbnail_file=thumbnail_filename,
        category_id=category_id,
        is_private=is_private,
    )

    video = video_crud.create_video(
        session=session,
        video_in=video_in,
        owner_id=current_user.id,
    )

    process_video.delay(filename)
    return video


@router.put("/{id}", response_model=VideoPublic)
def update_video_metadata(
    *,
    id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    title: str | None = None,
    description: str | None = None,
    category_id: uuid.UUID | None = None,
) -> Any:
    """
    Обновите метаданные для существующего видео.
    - Обновлять могут только владелец или администратор.
    - Содержимое файла само по себе не подлежит замене.
    """
    video = video_crud.get_video(session=session, video_id=id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.owner_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403, detail="Not authorized to update this video"
        )

    if title is None and description is None and category_id is None:
        raise HTTPException(status_code=400, detail="No update parameters provided")

    video_in = VideoUpdate(
        title=title or video.title,
        description=description if description is not None else video.description,
        category_id=category_id if category_id is not None else video.category_id,
    )

    updated = video_crud.update_video(
        session=session,
        video_id=id,
        video_in=video_in,
    )

    return updated


@router.get("/", response_model=VideosPublic)
def get_videos_list(
    *,
    session: SessionDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    sort: str = Query("new", regex="^(new|old)$"),
    category_id: uuid.UUID | None = Query(None),
    search: str | None = Query(None, min_length=1),
) -> Any:
    """
    List videos with filters:
    - sort=new|old       → by created_at desc/asc
    - category_id=<uuid> → only that category
    - search=<text>      → case‐insensitive substring in title or description
    """

    videos, count = video_crud.get_videos(
        session=session,
        skip=skip,
        limit=limit,
        sort_desc=(sort == "new"),
        category_id=category_id,
        search=search,
        viewer_id=None,
    )
    return VideosPublic(data=videos, count=count)


@router.get("/feed", response_model=VideosPublic)
def get_feed(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    sort: str = Query("new", regex="^(new|old)$"),
) -> Any:
    """
    Get the current user's feed: videos by authors they follow.
    - sort=new|old → newest first or oldest first
    - pagination via skip & limit
    """

    videos, count = video_crud.get_videos(
        session=session,
        skip=skip,
        limit=limit,
        sort_desc=(sort == "new"),
        category_id=None,
        search=None,
        viewer_id=current_user.id,  # only subscriptions
    )

    return VideosPublic(data=videos, count=count)


@router.get("/{id}", response_model=VideoPublic)
def get_video_by_id(id: uuid.UUID, session: SessionDep) -> Any:
    video = video_crud.get_video(session=session, video_id=id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.get("/{id}/stream")
def stream_video(id: str, session: SessionDep, request: Request):
    """
    Стриминг видео с поддержкой Range-запросов.
    """
    video = video_crud.get_video(session=session, video_id=id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    filename = video.filename
    file_path = UPLOAD_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")
    if range_header is None:

        def full_iterator():
            with open(file_path, "rb") as f:
                yield from iter(lambda: f.read(CHUNK_SIZE), b"")

        return StreamingResponse(
            full_iterator(),
            media_type="video/mp4",
            headers={"Content-Length": str(file_size)},
        )

    range_val = range_header.strip().lower().split("=")[-1]
    start_str, end_str = range_val.split("-")
    start = int(start_str) if start_str else 0
    end = int(end_str) if end_str else file_size - 1
    if end >= file_size:
        end = file_size - 1
    content_length = end - start + 1

    def range_iterator():
        with open(file_path, "rb") as f:
            f.seek(start)
            bytes_to_read = content_length
            while bytes_to_read > 0:
                chunk = f.read(min(CHUNK_SIZE, bytes_to_read))
                if not chunk:
                    break
                bytes_to_read -= len(chunk)
                yield chunk

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
    }

    return StreamingResponse(
        range_iterator(),
        status_code=206,
        media_type="video/mp4",
        headers=headers,
    )


@router.get("/{id}/thumbnail")
def get_video_thumbnail(id: str, session: SessionDep):
    """
    Получить обложку видео.
    """
    video = video_crud.get_video(session=session, video_id=id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if not video.thumbnail_filename:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    thumbnail_path = UPLOAD_DIR / video.thumbnail_filename
    if not thumbnail_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file missing")

    return FileResponse(thumbnail_path, media_type="image/jpeg")


@router.delete("/{id}")
def delete_video_by_id(
    id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Message:
    video = video_crud.get_video(session=session, video_id=id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    try:
        os.remove(UPLOAD_DIR / video.filename)
    except FileNotFoundError:
        pass
    video_crud.delete_video(session=session, video_id=id)
    return Message(message="Video deleted")


@router.post("/{id}/like", response_model=Message)
def toggle_like(
    id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Message:
    """
    Отметить видео как понравившееся:
    - Если еще не понравилось → нравится
    - Если уже понравилось → не нравится
    """
    video = video_crud.get_video(session=session, video_id=id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    existing = session.exec(
        select(VideoLike)
        .where(VideoLike.video_id == id)
        .where(VideoLike.user_id == current_user.id)
    ).first()

    if existing:
        session.delete(existing)
        session.commit()
        return Message(message="Like removed")

    new_link = VideoLike(
        video_id=id,
        user_id=current_user.id,
    )
    session.add(new_link)
    session.commit()
    return Message(message="Video liked")


@router.post("/{id}/view", response_model=Message)
async def register_video_view_by_id(
    id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Message:
    """
    Отметить видео как просмотренное.
    """
    video = video_crud.get_video(session=session, video_id=id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    user_id = current_user.id if current_user else None
    video_crud.view_video(session=session, user_id=user_id, video_id=id)

    return Message(message="Video view registered")


@router.get("/{id}/stats", response_model=VideoStats)
def get_video_stats(id: uuid.UUID, session: SessionDep) -> VideoStats:
    """
    Получить статистику по лайкам и просмотрам на видео.
    """
    video = video_crud.get_video(session=session, video_id=id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    views_count = session.exec(
        select(func.count()).select_from(VideoView).where(VideoView.video_id == id)
    ).one()

    likes_count = session.exec(
        select(func.count()).select_from(VideoLike).where(VideoLike.video_id == id)
    ).one()

    return VideoStats(views=views_count, likes=likes_count)
