"""
Media router — handles multi-format ingestion (video, audio, image),
status polling, event listing, and media streaming.
"""

import uuid
import shutil
import subprocess
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Header, Form
from fastapi.responses import FileResponse

from config import settings
from models.schemas import (
    VideoRecord, VideoStatus, TimelineEvent, EventType,
    VideoUploadResponse, VideoStatusResponse, EventsResponse,
)
import store
from services.frame_extractor import extract_frames
from services.vision_service import analyze_all_frames, analyze_single_image
from services.audio_service import transcribe_video
from services.event_merger import merge_events
from services.rag_service import index_events

router = APIRouter(prefix="/videos", tags=["videos"])


def _detect_media_type(filename: str, content_type: Optional[str] = None) -> str:
    ext = Path(filename).suffix.lower()
    ct = (content_type or "").lower()
    if ct.startswith("audio/") or ext in [".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma"]:
        return "audio"
    if ct.startswith("image/") or ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"]:
        return "image"
    if ct.startswith("video/") or ext in [".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"]:
        return "video"
    return "unknown"


def get_media_duration(file_path: Path) -> float:
    """Gets duration in seconds of any audio or video file using FFmpeg."""
    try:
        import imageio_ffmpeg
        ffmpeg_cmd = imageio_ffmpeg.get_ffmpeg_exe()
        res = subprocess.run(
            [ffmpeg_cmd, "-i", str(file_path)],
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
        if m:
            hours, mins, secs = m.groups()
            return round(int(hours) * 3600 + int(mins) * 60 + float(secs), 2)
    except Exception:
        pass
    return 0.0


# ─── Background processing pipeline ──────────────────────────────────────────

def process_video(video_id: str, api_key: Optional[str] = None):
    """Full processing pipeline supporting Video, Audio, and Image media."""
    video = store.get_video(video_id)
    if not video:
        return

    try:
        video.status = VideoStatus.PROCESSING
        store.update_video(video)

        media_type = getattr(video, "media_type", "video") or "video"
        dest_path = settings.storage_dir / "videos" / video.filename

        if media_type == "image":
            # ── 1. Image analysis ─────────────────────────────────────────────
            visual_events = analyze_single_image(str(dest_path), groq_api_key=api_key)
            video.duration_seconds = 0.0
            video.frame_count = 1

            # Cache copy into frames directory
            frames_dir = settings.storage_dir / "frames" / video.id
            frames_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest_path, frames_dir / "frame_00000.jpg")

            timeline = [
                TimelineEvent(
                    id=str(uuid.uuid4()),
                    timestamp=round(float(ve.timestamp), 2),
                    modality="visual",
                    event_type=ve.event_type,
                    description=ve.description,
                    confidence=ve.confidence,
                    raw_visual=ve,
                )
                for ve in visual_events
            ]

        elif media_type == "audio":
            # ── 2. Audio transcription ────────────────────────────────────────
            duration = get_media_duration(dest_path)
            video.duration_seconds = duration
            video.frame_count = 0

            audio_events = transcribe_video(video.id, video.filename, groq_api_key=api_key)
            if not audio_events:
                timeline = [
                    TimelineEvent(
                        id=str(uuid.uuid4()),
                        timestamp=0.0,
                        modality="audio",
                        event_type=EventType.OTHER,
                        description="Audio file analyzed. No distinct speech was detected.",
                        confidence=0.9,
                    )
                ]
            else:
                timeline = [
                    TimelineEvent(
                        id=str(uuid.uuid4()),
                        timestamp=round(float(ae.timestamp), 2),
                        modality="audio",
                        event_type=EventType.SPEECH,
                        description=f"🗣️ \"{ae.text}\"",
                        confidence=ae.confidence,
                        raw_audio=ae,
                    )
                    for ae in audio_events
                ]

        else:
            # ── 3. Video processing ───────────────────────────────────────────
            frames, duration = extract_frames(video)
            video.duration_seconds = duration
            video.frame_count = len(frames)

            visual_events = analyze_all_frames(frames, groq_api_key=api_key)
            audio_events = transcribe_video(video.id, video.filename, groq_api_key=api_key)
            timeline = merge_events(visual_events, audio_events)

        # Index in ChromaDB for RAG
        index_events(video_id, timeline)

        # Persist events
        store.save_events(video_id, timeline)

        # Update video record
        video.status = VideoStatus.COMPLETED
        video.processed_at = datetime.utcnow()
        store.update_video(video)

    except Exception as e:
        video.status = VideoStatus.FAILED
        video.error = str(e)
        store.update_video(video)
        print(f"[ProcessMedia] Error for {video_id}: {e}")


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("", response_model=VideoUploadResponse)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_groq_api_key: Optional[str] = Header(None, alias="X-Groq-Api-Key"),
    api_key: Optional[str] = Form(None),
):
    """Upload a video, audio, or image file and start async processing."""
    client_key = (x_groq_api_key or api_key or "").strip() or None
    media_type = _detect_media_type(file.filename or "", file.content_type)
    if media_type == "unknown":
        raise HTTPException(
            status_code=400,
            detail="Unsupported format. Please upload a Video (MP4, MOV, WEBM), Audio (MP3, WAV, M4A), or Image (JPG, PNG, WEBP)."
        )

    video_id = str(uuid.uuid4())
    ext = Path(file.filename or f"media_{video_id}").suffix
    if not ext:
        if media_type == "image": ext = ".jpg"
        elif media_type == "audio": ext = ".mp3"
        else: ext = ".mp4"

    filename = f"{video_id}{ext}"
    dest = settings.storage_dir / "videos" / filename

    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)

    video = VideoRecord(
        id=video_id,
        filename=filename,
        original_name=file.filename or filename,
        media_type=media_type,
        status=VideoStatus.PENDING,
    )
    store.save_video(video)

    # Kick off processing in the background with client's API key if provided
    background_tasks.add_task(process_video, video_id, client_key)

    return VideoUploadResponse(
        video_id=video_id,
        media_type=media_type,
        status=VideoStatus.PENDING,
        message=f"{media_type.capitalize()} uploaded. AI analysis started.",
    )


@router.get("", response_model=list[VideoStatusResponse])
async def list_videos():
    """List all media."""
    videos = store.list_videos()
    return [
        VideoStatusResponse(
            video_id=v.id,
            media_type=getattr(v, "media_type", "video"),
            status=v.status,
            duration_seconds=v.duration_seconds,
            frame_count=v.frame_count,
            event_count=len(store.get_events(v.id)),
            error=v.error,
        )
        for v in videos
    ]


@router.get("/{video_id}/status", response_model=VideoStatusResponse)
async def get_status(video_id: str):
    """Poll media processing status."""
    video = store.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Media not found.")

    return VideoStatusResponse(
        video_id=video.id,
        media_type=getattr(video, "media_type", "video"),
        status=video.status,
        duration_seconds=video.duration_seconds,
        frame_count=video.frame_count,
        event_count=len(store.get_events(video_id)),
        error=video.error,
    )


@router.get("/{video_id}/events", response_model=EventsResponse)
async def get_events(video_id: str):
    """Get the processed timeline events for media."""
    video = store.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Media not found.")
    if video.status != VideoStatus.COMPLETED:
        raise HTTPException(status_code=202, detail=f"Media is still {video.status.value}.")

    events = store.get_events(video_id)
    return EventsResponse(video_id=video_id, events=events, total=len(events))


@router.get("/{video_id}/media")
async def get_media_file(video_id: str):
    """Stream or serve the original uploaded media file."""
    video = store.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Media not found.")
    media_path = settings.storage_dir / "videos" / video.filename
    if not media_path.exists():
        raise HTTPException(status_code=404, detail="Media file not found on disk.")

    media_type = getattr(video, "media_type", "video")
    ext = media_path.suffix.lower()

    if media_type == "image":
        media_content_type = "image/png" if ext == ".png" else "image/webp" if ext == ".webp" else "image/jpeg"
    elif media_type == "audio":
        media_content_type = "audio/wav" if ext == ".wav" else "audio/mp4" if ext == ".m4a" else "audio/mpeg"
    else:
        media_content_type = "video/webm" if ext == ".webm" else "video/mp4"

    return FileResponse(
        path=str(media_path),
        media_type=media_content_type,
        filename=video.original_name
    )
