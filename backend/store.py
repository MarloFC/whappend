"""
Database-backed media store (Postgres / SQLite via SQLAlchemy).
Persists Media records, timeline events (JSON/JSONB), and chapters (JSON/JSONB),
scoped per user.
"""

from datetime import timezone
from typing import Optional
from sqlalchemy import select

from db.base import session_scope
from db.models import Media
from models.schemas import ChaptersResponse, TimelineEvent, VideoRecord, VideoStatus


def _row_to_video_record(row: Media) -> VideoRecord:
    return VideoRecord(
        id=row.id,
        user_id=row.user_id,
        filename=row.filename,
        original_name=row.original_name,
        media_type=row.media_type,
        status=VideoStatus(row.status),
        source=row.source or "web",
        duration_seconds=row.duration_seconds,
        frame_count=row.frame_count,
        created_at=row.created_at,
        processed_at=row.processed_at,
        error=row.error,
    )


def save_video(video: VideoRecord, user_id: Optional[str] = None, source: str = "web") -> VideoRecord:
    effective_user_id = user_id or getattr(video, "user_id", None)
    if not effective_user_id:
        raise ValueError("user_id is required when saving a media record.")

    with session_scope() as db:
        row = db.get(Media, video.id)
        if row is None:
            row = Media(
                id=video.id,
                user_id=effective_user_id,
                filename=video.filename,
                original_name=video.original_name,
                media_type=video.media_type,
                status=video.status.value if isinstance(video.status, VideoStatus) else str(video.status),
                source=source or getattr(video, "source", "web") or "web",
                duration_seconds=video.duration_seconds,
                frame_count=video.frame_count,
                created_at=video.created_at,
                processed_at=video.processed_at,
                error=video.error,
            )
            db.add(row)
        else:
            row.status = video.status.value if isinstance(video.status, VideoStatus) else str(video.status)
            row.duration_seconds = video.duration_seconds
            row.frame_count = video.frame_count
            row.processed_at = video.processed_at
            row.error = video.error
        db.flush()
        return _row_to_video_record(row)


def get_video(video_id: str, user_id: Optional[str] = None) -> Optional[VideoRecord]:
    with session_scope() as db:
        row = db.get(Media, video_id)
        if not row:
            return None
        if user_id and row.user_id != user_id:
            return None
        return _row_to_video_record(row)


def list_videos(user_id: Optional[str] = None) -> list[VideoRecord]:
    with session_scope() as db:
        stmt = select(Media).order_by(Media.created_at.desc())
        if user_id:
            stmt = stmt.where(Media.user_id == user_id)
        rows = db.execute(stmt).scalars().all()
        return [_row_to_video_record(r) for r in rows]


def update_video(video: VideoRecord) -> VideoRecord:
    with session_scope() as db:
        row = db.get(Media, video.id)
        if not row:
            raise ValueError(f"Media {video.id} not found.")
        row.status = video.status.value if isinstance(video.status, VideoStatus) else str(video.status)
        row.duration_seconds = video.duration_seconds
        row.frame_count = video.frame_count
        row.processed_at = video.processed_at
        row.error = video.error
        db.flush()
        return _row_to_video_record(row)


def save_events(video_id: str, events: list[TimelineEvent]) -> None:
    serialized = [e.model_dump(mode="json") for e in events]
    with session_scope() as db:
        row = db.get(Media, video_id)
        if row:
            row.events = serialized
            db.flush()


def get_events(video_id: str) -> list[TimelineEvent]:
    with session_scope() as db:
        row = db.get(Media, video_id)
        if not row or not row.events:
            return []
        return [TimelineEvent.model_validate(item) for item in row.events]


def save_chapters(video_id: str, chapters: ChaptersResponse) -> ChaptersResponse:
    with session_scope() as db:
        row = db.get(Media, video_id)
        if row:
            row.chapters = chapters.model_dump(mode="json")
            db.flush()
    return chapters


def get_chapters(video_id: str) -> Optional[ChaptersResponse]:
    with session_scope() as db:
        row = db.get(Media, video_id)
        if not row or not row.chapters:
            return None
        return ChaptersResponse.model_validate(row.chapters)
