import logging
import subprocess
from pathlib import Path

from sqlmodel import Session, select

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.db import engine
from app.models import Video


@celery_app.task(name="app.tasks.video.process_video")
def process_video(filename: str) -> None:
    logging.info(f"🎬 Starting to process video: {filename}")

    input_path = settings.UPLOAD_DIR / filename
    output_filename = f"{Path(filename).stem}.mp4"
    output_path = settings.UPLOAD_DIR / output_filename

    # Конвертация в .mp4
    if not filename.endswith(".mp4"):
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(input_path),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    str(output_path),
                ],
                check=True,
            )

            # Обновление имени файла в БД
            with Session(engine) as session:
                video = session.exec(
                    select(Video).where(Video.filename == filename)
                ).first()
                if video:
                    video.filename = output_filename
                    session.add(video)
                    session.commit()

            input_path.unlink(missing_ok=True)
            logging.info(f"✅ Video converted to mp4: {output_filename}")
        except subprocess.CalledProcessError as e:
            logging.error(f"❌ Error converting video: {e}")
            return
    else:
        output_path = input_path

    # Генерация превью
    with Session(engine) as session:
        video = session.exec(
            select(Video).where(Video.filename == output_filename)
        ).first()
        if video and not video.thumbnail_filename:
            thumbnail_filename = f"{Path(output_filename).stem}_auto.jpg"
            thumbnail_path = settings.UPLOAD_DIR / thumbnail_filename

            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(output_path),
                        "-ss",
                        "00:00:01.000",
                        "-vframes",
                        "1",
                        str(thumbnail_path),
                    ],
                    check=True,
                )

                video.thumbnail_filename = thumbnail_filename
                session.add(video)
                session.commit()
                logging.info(f"🖼️  Thumbnail generated: {thumbnail_filename}")
            except subprocess.CalledProcessError as e:
                logging.error(f"❌ Error generating thumbnail: {e}")

    logging.info(f"✅ Finished processing video: {output_filename}")
