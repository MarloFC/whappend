"""
Frame extractor service.
Uses OpenCV + FFmpeg to pull one frame every N seconds from the video.
"""

import cv2
import os
from pathlib import Path

from config import settings
from models.schemas import VideoRecord


def extract_frames(video: VideoRecord) -> list[dict]:
    """
    Extract frames at a fixed interval from the video file.

    Returns a list of dicts:
        [{"timestamp": float, "path": str}, ...]
    """
    video_path = settings.storage_dir / "videos" / video.filename
    frames_dir = settings.storage_dir / "frames" / video.id
    frames_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video file: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0

    interval_frames = int(fps * settings.frame_interval_seconds)
    frame_index = 0
    extracted = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_index % interval_frames == 0:
            timestamp = frame_index / fps
            frame_filename = f"frame_{int(timestamp):05d}.jpg"
            frame_path = frames_dir / frame_filename

            # Resize to reduce token cost: max width 1024px
            h, w = frame.shape[:2]
            if w > 1024:
                scale = 1024 / w
                frame = cv2.resize(frame, (1024, int(h * scale)))

            cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            extracted.append({"timestamp": round(timestamp, 2), "path": str(frame_path)})

        frame_index += 1

    cap.release()
    return extracted, duration
