"""
Audio service.
Runs Groq Whisper API (whisper-large-v3-turbo) or local faster-whisper.
"""

import os
import random
import subprocess
import tempfile
from typing import Optional
from config import settings
from models.schemas import AudioEvent


def _get_ffmpeg_cmd() -> str:
    """Finds available FFmpeg executable from imageio_ffmpeg or system PATH."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


# ─── Mock mode ────────────────────────────────────────────────────────────────

_MOCK_SPEECH = [
    "Can you send me the report?",
    "Let me pull that up right now.",
    "Yeah, I think we should go with option two.",
    "Hold on, let me check the numbers.",
    "Okay, I'll have it done by end of day.",
]


def _mock_transcribe() -> list[AudioEvent]:
    events = []
    t = random.uniform(3.0, 8.0)
    for _ in range(random.randint(2, 4)):
        text = random.choice(_MOCK_SPEECH)
        duration = random.uniform(2.0, 5.0)
        events.append(AudioEvent(
            timestamp=round(t, 2),
            end_timestamp=round(t + duration, 2),
            text=text,
            confidence=round(random.uniform(0.80, 0.98), 2),
        ))
        t += duration + random.uniform(3.0, 8.0)
    return events


# ─── Local Whisper via faster-whisper (free, CPU) ─────────────────────────────

_whisper_model = None


def _get_local_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        print("[AudioService] Loading faster-whisper model 'base' on CPU…")
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        print("[AudioService] Whisper loaded.")
    return _whisper_model


def _transcribe_local(filename: str) -> list[AudioEvent]:
    video_path = settings.storage_dir / "videos" / filename
    ffmpeg_cmd = _get_ffmpeg_cmd()

    # Extract audio to temp file first for cleaner decoding
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        cmd = [ffmpeg_cmd, "-y", "-i", str(video_path), "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k", tmp_path]
        subprocess.run(cmd, capture_output=True, check=True)

        model = _get_local_model()
        segments, _info = model.transcribe(tmp_path, beam_size=5)
        events = []
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            events.append(AudioEvent(
                timestamp=round(float(seg.start), 2),
                end_timestamp=round(float(seg.end), 2),
                text=text,
                confidence=round(max(0.0, min(1.0, seg.avg_logprob + 1.0)), 2),
            ))
        return events
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


# ─── Groq Whisper API ─────────────────────────────────────────────────────────

def _transcribe_groq(filename: str, groq_api_key: Optional[str] = None) -> list[AudioEvent]:
    """
    Groq supports OpenAI-compatible Whisper API.
    Extracts audio via FFmpeg and sends to Groq whisper-large-v3-turbo.
    """
    from groq import Groq

    video_path = settings.storage_dir / "videos" / filename
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    effective_key = groq_api_key or settings.groq_api_key
    if not effective_key:
        raise ValueError("Groq API key is missing.")

    client = Groq(api_key=effective_key)
    ffmpeg_cmd = _get_ffmpeg_cmd()

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        cmd = [
            ffmpeg_cmd, "-y", "-i", str(video_path),
            "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k",
            tmp_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg audio extraction error: {res.stderr}")

        with open(tmp_path, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=audio_file,
                response_format="verbose_json",
            )

        segments = getattr(response, "segments", []) or []
        if not segments and getattr(response, "text", ""):
            text = getattr(response, "text", "").strip()
            if text:
                return [AudioEvent(timestamp=0.0, end_timestamp=0.0, text=text, confidence=0.95)]

        events = _segments_to_events(segments)
        print(f"[AudioService] Transcribed {len(events)} audio speech segments via Groq Whisper.")
        return events
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _segments_to_events(segments: list) -> list[AudioEvent]:
    events = []
    for seg in segments:
        if isinstance(seg, dict):
            start = seg.get("start", 0)
            end = seg.get("end", start + 1)
            text = seg.get("text", "").strip()
            logprob = seg.get("avg_logprob", -0.5)
        else:
            start = getattr(seg, "start", 0)
            end = getattr(seg, "end", start + 1)
            text = getattr(seg, "text", "").strip()
            logprob = getattr(seg, "avg_logprob", -0.5)

        if not text:
            continue

        confidence = max(0.0, min(1.0, logprob + 1.0))
        events.append(AudioEvent(
            timestamp=round(float(start), 2),
            end_timestamp=round(float(end), 2),
            text=text,
            confidence=round(confidence, 2),
        ))
    return events


# ─── Public API ───────────────────────────────────────────────────────────────

def transcribe_video(video_id: str, filename: str, groq_api_key: Optional[str] = None) -> list[AudioEvent]:
    if settings.mock_mode:
        return _mock_transcribe()

    effective_groq = groq_api_key or settings.groq_api_key
    if effective_groq:
        try:
            return _transcribe_groq(filename, groq_api_key=effective_groq)
        except Exception as e:
            print(f"[AudioService] Groq Whisper error ({e}), attempting local fallback...")

    try:
        return _transcribe_local(filename)
    except Exception as e:
        print(f"[AudioService] Audio processing notice ({e}). No speech detected.")
        return []
