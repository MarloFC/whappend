"""
In-memory video store (replace with SQLite/Postgres in production).
Stores VideoRecord objects and their associated timeline events.
"""

from models.schemas import VideoRecord, TimelineEvent

_videos: dict[str, VideoRecord] = {}
_events: dict[str, list[TimelineEvent]] = {}


def save_video(video: VideoRecord) -> VideoRecord:
    _videos[video.id] = video
    return video


def get_video(video_id: str) -> VideoRecord | None:
    return _videos.get(video_id)


def list_videos() -> list[VideoRecord]:
    return list(_videos.values())


def update_video(video: VideoRecord) -> VideoRecord:
    _videos[video.id] = video
    return video


def save_events(video_id: str, events: list[TimelineEvent]) -> None:
    _events[video_id] = events


def get_events(video_id: str) -> list[TimelineEvent]:
    return _events.get(video_id, [])
