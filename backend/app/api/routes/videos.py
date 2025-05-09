import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlmodel import func, select

from app.api.deps import CurrentUser, SessionDep
from app.models import Video
from app.schemas import Message, VideoPublic, VideosPublic

UPLOAD_DIR = Path("uploads") / "videos"
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
    file: UploadFile = File(...),
) -> Any:
    """
    Upload a video. Max duration: 5 minutes. Saved to local `uploads/`.
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

    # Save metadata
    video = Video(
        id=video_id,
        title=title,
        description=description,
        filename=filename,
        owner_id=current_user.id,
    )
    session.add(video)
    session.commit()
    session.refresh(video)

    # Start postprocessing in background (via Celery stub)
    # background_tasks.add_task(fake_video_postprocess, video.id, str(filepath))

    return video


@router.get("/", response_model=VideosPublic)
def get_videos(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    count_stmt = select(func.count()).select_from(Video)
    data_stmt = select(Video).offset(skip).limit(limit)
    count = session.exec(count_stmt).one()
    videos = session.exec(data_stmt).all()
    return VideosPublic(data=videos, count=count)


@router.get("/{id}", response_model=VideoPublic)
def get_video(id: uuid.UUID, session: SessionDep) -> Any:
    video = session.get(Video, id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.get("/{id}/stream")
def stream_video(id: str, session: SessionDep, request: Request):
    """
    Стриминг видео с поддержкой Range-запросов.
    """
    video = session.get(Video, id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    filename = f"{id}.mp4"  # пример
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


@router.delete("/{id}")
def delete_video(
    id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Message:
    video = session.get(Video, id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    try:
        os.remove(UPLOAD_DIR / video.filename)
    except FileNotFoundError:
        pass
    session.delete(video)
    session.commit()
    return Message(message="Video deleted")
