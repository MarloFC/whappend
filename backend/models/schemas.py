from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid
from datetime import datetime


# ─── Enums ────────────────────────────────────────────────────────────────────

class VideoStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EventType(str, Enum):
    PERSON_ENTERS = "person_enters"
    PERSON_EXITS = "person_exits"
    PERSON_SITS = "person_sits"
    PERSON_STANDS = "person_stands"
    OBJECT_APPEARS = "object_appears"
    OBJECT_REMOVED = "object_removed"
    ACTION = "action"
    SPEECH = "speech"
    SCENE_CHANGE = "scene_change"
    OTHER = "other"


# ─── Events ───────────────────────────────────────────────────────────────────

class VisualEvent(BaseModel):
    timestamp: float
    event_type: EventType
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    objects: list[str] = []


class AudioEvent(BaseModel):
    timestamp: float
    end_timestamp: float
    text: str
    speaker: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)


class TimelineEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float
    modality: str  # "visual" | "audio" | "merged"
    event_type: EventType
    description: str
    confidence: float
    raw_visual: Optional[VisualEvent] = None
    raw_audio: Optional[AudioEvent] = None


# ─── Video ────────────────────────────────────────────────────────────────────

class VideoRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    original_name: str
    media_type: str = "video"  # "video" | "audio" | "image"
    status: VideoStatus = VideoStatus.PENDING
    duration_seconds: Optional[float] = None
    frame_count: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    error: Optional[str] = None


# ─── API Schemas ──────────────────────────────────────────────────────────────

class VideoUploadResponse(BaseModel):
    video_id: str
    media_type: str = "video"
    status: VideoStatus
    message: str


class VideoStatusResponse(BaseModel):
    video_id: str
    media_type: str = "video"
    status: VideoStatus
    duration_seconds: Optional[float]
    frame_count: Optional[int]
    event_count: Optional[int]
    error: Optional[str]


class EventsResponse(BaseModel):
    video_id: str
    events: list[TimelineEvent]
    total: int


class QuestionRequest(BaseModel):
    question: str
    video_id: str
    groq_api_key: Optional[str] = None


class QuestionResponse(BaseModel):
    answer: str
    relevant_events: list[TimelineEvent]
    video_id: str
