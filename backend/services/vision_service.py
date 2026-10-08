"""
Vision service.
Supports: OpenAI, Gemini, Groq, Real OpenCV Computer Vision, or Mock mode.
"""

import base64
import json
import random
from typing import Optional
from config import settings
from models.schemas import VisualEvent, EventType

SYSTEM_PROMPT = """You are a video analysis assistant.
You receive a batch of video frames with their timestamps.
For each frame, identify key events happening — people, objects, actions, scene changes.
Return ONLY a valid JSON array. No prose, no markdown, no explanation.

Format:
[
  {
    "timestamp": <number>,
    "event_type": "<one of: person_enters, person_exits, person_sits, person_stands, object_appears, object_removed, action, scene_change, other>",
    "description": "<concise description of what is happening>",
    "confidence": <0.0 to 1.0>,
    "objects": ["<object1>", "<object2>"]
  }
]

Only include frames where something notable is happening. Skip static/unchanged frames.
If nothing notable is happening in any frame, return an empty array: []
"""


def _encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _parse_events(raw: str, frames: list[dict]) -> list[VisualEvent]:
    """Parse LLM JSON output into VisualEvent list. Robust to markdown fences and surrounding text."""
    import re
    raw = raw.strip()
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
        if m:
            raw = m.group(1).strip()

    # If surrounded by explanatory text, extract [ ... ]
    if not (raw.startswith("[") and raw.endswith("]")):
        m = re.search(r"\[\s*\{[\s\S]*\}\s*\]", raw)
        if m:
            raw = m.group(0)
        elif raw.startswith("{") and raw.endswith("}"):
            raw = f"[{raw}]"

    try:
        events_data = json.loads(raw)
    except Exception:
        # Attempt to recover truncated JSON array if generation was cut short
        last_brace = raw.rfind("}")
        if last_brace != -1:
            try:
                repaired = raw[:last_brace + 1].strip()
                if not repaired.endswith("]"):
                    repaired += "]"
                events_data = json.loads(repaired)
            except Exception as e:
                print(f"[VisionService] Failed to parse JSON from LLM: {e}. Raw snippet: {raw[:150]}")
                return []
        else:
            print(f"[VisionService] Failed to parse JSON from LLM. Raw snippet: {raw[:150]}")
            return []

    events = []
    for item in events_data:
        try:
            event = VisualEvent(
                timestamp=float(item["timestamp"]),
                event_type=EventType(item.get("event_type", "other")),
                description=item["description"],
                confidence=min(max(float(item.get("confidence", 0.8)), 0.0), 1.0),
                objects=item.get("objects", []),
            )
            events.append(event)
        except Exception as e:
            print(f"[VisionService] Skipping malformed event: {e}")
    return events


# ─── Real OpenCV Computer Vision Analysis ─────────────────────────────────────

def _analyze_opencv(frames: list[dict]) -> list[VisualEvent]:
    """
    Real Computer Vision Analysis using OpenCV.
    Calculates frame-by-frame visual differences, motion intensity,
    and histogram changes directly from the extracted image files.
    """
    import cv2
    import numpy as np

    events = []
    prev_gray = None
    prev_hist = None

    for i, frame in enumerate(frames):
        path = frame.get("path")
        ts = frame.get("timestamp", 0.0)
        img = cv2.imread(path)
        if img is None:
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([img], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        cv2.normalize(hist, hist)

        if prev_gray is not None and prev_hist is not None:
            # 1. Calculate frame difference (motion intensity)
            diff = cv2.absdiff(gray, prev_gray)
            motion_score = float(np.mean(diff) / 255.0)  # Normalized 0.0 to 1.0

            # 2. Calculate histogram distance (scene cut / camera switch)
            hist_sim = float(cv2.compareHist(hist, prev_hist, cv2.HISTCMP_CORREL))
            scene_change_score = 1.0 - max(0.0, hist_sim)

            # Determine event type based on real OpenCV metrics
            if scene_change_score > 0.45:
                events.append(VisualEvent(
                    timestamp=ts,
                    event_type=EventType.SCENE_CHANGE,
                    description=f"Visual scene change / camera cut detected (transition metric: {scene_change_score:.2f})",
                    confidence=round(min(1.0, 0.7 + scene_change_score * 0.3), 2),
                    objects=["scene", "camera"],
                ))
            elif motion_score > 0.06:
                events.append(VisualEvent(
                    timestamp=ts,
                    event_type=EventType.ACTION,
                    description=f"Visual motion activity detected in frame (motion intensity: {motion_score:.2f})",
                    confidence=round(min(1.0, 0.6 + motion_score * 1.5), 2),
                    objects=["subject", "movement"],
                ))
            elif i == len(frames) - 1:
                events.append(VisualEvent(
                    timestamp=ts,
                    event_type=EventType.OTHER,
                    description="Stable frame state recorded",
                    confidence=0.85,
                    objects=["frame"],
                ))
        elif i == 0:
            events.append(VisualEvent(
                timestamp=ts,
                event_type=EventType.OTHER,
                description="Video initial frame established",
                confidence=0.90,
                objects=["scene"],
            ))

        prev_gray = gray
        prev_hist = hist

    return events


# ─── Mock mode ────────────────────────────────────────────────────────────────

_MOCK_DESCRIPTIONS = [
    ("person_enters", "A person enters the scene from the left"),
    ("action", "Person appears to be working at a desk"),
    ("person_sits", "Person sits down on a chair"),
    ("object_appears", "A laptop is opened on the desk"),
    ("speech", "Person gestures while speaking"),
    ("scene_change", "Camera angle changes"),
    ("person_exits", "Person walks out of frame"),
    ("action", "Person picks up a phone"),
]


def _mock_analyze(frames: list[dict]) -> list[VisualEvent]:
    events = []
    for i, frame in enumerate(frames):
        if random.random() < 0.6:  # ~60% of frames have events
            et, desc = random.choice(_MOCK_DESCRIPTIONS)
            events.append(VisualEvent(
                timestamp=frame["timestamp"],
                event_type=EventType(et),
                description=desc,
                confidence=round(random.uniform(0.70, 0.97), 2),
                objects=random.sample(["person", "desk", "laptop", "chair", "phone"], 2),
            ))
    return events


# ─── Gemini provider ──────────────────────────────────────────────────────────

def _analyze_gemini(frames: list[dict]) -> list[VisualEvent]:
    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError("Gemini API key is missing.")

    from google import genai
    from google.genai import types
    from PIL import Image

    client = genai.Client(api_key=api_key)

    contents = [SYSTEM_PROMPT, "Analyze these video frames and return structured JSON events."]
    for frame in frames:
        contents.append(f"[Timestamp: {frame['timestamp']}s]")
        img = Image.open(frame['path'])
        contents.append(img)

    response = client.models.generate_content(
        model=settings.gemini_vision_model,
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=1500,
        )
    )
    return _parse_events(response.text or "", frames)


# ─── Groq provider (Composite frame collage + backoff) ───────────────────────

GROQ_SYSTEM_PROMPT = """You are an expert video timeline event analyzer.
You receive a collage of sequential video frames with their timestamps labeled in corner badges (e.g. [0.0s], [2.0s]).
Identify key events happening across these frames (actions, speaking/gesturing, person entering/exiting, objects moved/used, scene transitions).
Return ONLY a valid JSON array of at most 2-3 most significant events. No markdown fences, no explanatory text.

Format:
[
  {
    "timestamp": <number matching the frame badge timestamp>,
    "event_type": "<one of: person_enters, person_exits, person_sits, person_stands, object_appears, object_removed, action, scene_change, other>",
    "description": "<concise description, maximum 10 words>",
    "confidence": 0.9,
    "objects": ["<object1>"]
  }
]
Keep each description strictly under 10 words. Only output notable actions or changes.
"""


def _encode_composite_frames(frames: list[dict]) -> str:
    """
    Stitches up to 4 video frames into a single composite collage image
    with timestamp badges overlaid. This allows multiple frames to be analyzed
    in ONE single vision API call, completely avoiding Groq's 3-image limit
    and cutting API calls and token consumption by 4x.
    """
    import cv2
    import numpy as np

    if not frames:
        return ""

    target_w, target_h = 480, 270
    tiles = []

    for frame in frames:
        img = cv2.imread(frame["path"])
        if img is None:
            img = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        else:
            img = cv2.resize(img, (target_w, target_h))

        ts = frame.get("timestamp", 0.0)
        ts_text = f"[{ts:.1f}s]"
        # Draw dark badge background & bright yellow text
        cv2.rectangle(img, (8, 8), (120, 36), (0, 0, 0), -1)
        cv2.putText(img, ts_text, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
        tiles.append(img)

    n = len(tiles)
    if n == 1:
        composite = tiles[0]
    elif n == 2:
        composite = np.hstack([tiles[0], tiles[1]])
    else:
        while len(tiles) < 4:
            tiles.append(np.zeros((target_h, target_w, 3), dtype=np.uint8))
        top_row = np.hstack([tiles[0], tiles[1]])
        bottom_row = np.hstack([tiles[2], tiles[3]])
        composite = np.vstack([top_row, bottom_row])

    _, buffer = cv2.imencode(".jpg", composite, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buffer.tobytes()).decode("utf-8")


def _call_groq_vision_with_backoff(
    client,
    messages: list,
    max_retries: int = 3,
    initial_tokens: int = 320,
    min_tokens: int = 160,
) -> str:
    """
    Calls Groq Vision API with exponential backoff on 429 (rate limit / OTPM exceeded)
    and 503 (model overloaded), dynamically throttling token reservations.
    """
    import time
    import re

    current_tokens = initial_tokens
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=settings.groq_vision_model,
                messages=messages,
                max_tokens=current_tokens,
                temperature=0.1,
            )
            return response.choices[0].message.content or "[]"
        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "rate_limit" in err_str.lower() or "too large" in err_str.lower()
            is_overload = "503" in err_str or "overloaded" in err_str.lower() or "service unavailable" in err_str.lower()

            if (is_rate_limit or is_overload) and attempt < max_retries:
                # Default backoff: 8s, 16s, 24s
                wait_time = 8.0 * (attempt + 1)

                # Try parsing explicit wait duration if returned by Groq
                match = re.search(r"try again in ([0-9.]+)s", err_str, re.IGNORECASE)
                if match:
                    wait_time = float(match.group(1)) + 1.5

                print(f"[VisionService] Groq API rate-limit/overload (attempt {attempt + 1}/{max_retries}). Cooldown for {wait_time:.1f}s...")
                current_tokens = max(min_tokens, current_tokens - 40)
                time.sleep(wait_time)
            else:
                raise


def _analyze_groq(frames: list[dict], groq_api_key: Optional[str] = None) -> list[VisualEvent]:
    """
    Groq vision analysis using composite frame collage and backoff retry.
    Encodes up to 4 frames as a single image, strictly complying with
    Groq's 3-image max limit and preserving token quota.
    """
    effective_key = groq_api_key or settings.groq_api_key
    if not effective_key:
        raise ValueError("Groq API key is missing.")
    from groq import Groq
    client = Groq(api_key=effective_key)

    if not frames:
        return []

    # Encode all frames in this batch into one single composite image
    b64_image = _encode_composite_frames(frames)
    ts_list = ", ".join(f"[{f['timestamp']:.1f}s]" for f in frames)

    messages = [
        {"role": "system", "content": GROQ_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Analyze these consecutive frames at timestamps {ts_list}. Return JSON array of notable events."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_image}"
                    }
                }
            ]
        }
    ]

    raw_output = _call_groq_vision_with_backoff(client, messages)
    return _parse_events(raw_output, frames)


# ─── OpenAI provider ──────────────────────────────────────────────────────────

def _analyze_openai(frames: list[dict]) -> list[VisualEvent]:
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key is missing.")
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)

    content = [
        {"type": "text",
         "text": f"Analyze these {len(frames)} video frames and return structured events as JSON."}
    ]
    for frame in frames:
        content.append({"type": "text", "text": f"[Timestamp: {frame['timestamp']}s]"})
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{_encode_image(frame['path'])}",
                "detail": "low"
            }
        })

    response = client.chat.completions.create(
        model=settings.openai_vision_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        max_tokens=1500,
        temperature=0.1,
    )
    return _parse_events(response.choices[0].message.content, frames)


# ─── Public API ───────────────────────────────────────────────────────────────

def analyze_frame_batch(frames: list[dict], groq_api_key: Optional[str] = None) -> list[VisualEvent]:
    if settings.mock_mode:
        return _mock_analyze(frames)

    effective_groq = groq_api_key or settings.groq_api_key
    provider = (settings.llm_provider or "").lower()
    if provider == "gemini" and settings.gemini_api_key:
        return _analyze_gemini(frames)
    elif provider == "openai" and settings.openai_api_key:
        return _analyze_openai(frames)
    elif (provider == "groq" or effective_groq) and effective_groq:
        return _analyze_groq(frames, groq_api_key=effective_groq)
    
    # Try any available API key if specific provider key isn't present
    if settings.gemini_api_key:
        return _analyze_gemini(frames)
    if settings.openai_api_key:
        return _analyze_openai(frames)

    # Fall back to Real OpenCV Computer Vision analysis on the actual video frames
    return _analyze_opencv(frames)


def analyze_all_frames(frames: list[dict], groq_api_key: Optional[str] = None) -> list[VisualEvent]:
    import time
    batch_size = settings.frame_batch_size
    all_events: list[VisualEvent] = []

    for i in range(0, len(frames), batch_size):
        batch = frames[i: i + batch_size]
        try:
            batch_events = analyze_frame_batch(batch, groq_api_key=groq_api_key)
            all_events.extend(batch_events)
        except Exception as e:
            print(f"[VisionService] Vision API error at batch {i}: {e}. Processing via Real OpenCV Computer Vision.")
            all_events.extend(_analyze_opencv(batch))

        # Smooth pacing between batches to respect Groq OTPM rate limits
        if i + batch_size < len(frames):
            time.sleep(2.0)

    return all_events


def analyze_single_image(image_path: str, groq_api_key: Optional[str] = None) -> list[VisualEvent]:
    """
    Analyzes a standalone image file using Vision AI to extract:
    - Scene setting & environment
    - Key subjects & actions
    - Prominent objects detected
    - Visible text / signage / typography
    """
    if settings.mock_mode:
        return [
            VisualEvent(
                timestamp=0.0,
                event_type=EventType.SCENE_CHANGE,
                description="Visual scene environment identified",
                confidence=0.92,
                objects=["scene", "subject"],
            ),
            VisualEvent(
                timestamp=0.0,
                event_type=EventType.OBJECT_APPEARS,
                description="Main subject and objects identified",
                confidence=0.95,
                objects=["object", "details"],
            )
        ]

    prompt = (
        "You are an expert image analyst. Examine this image in depth and describe it in rich detail.\n"
        "Return ONLY a valid JSON array (no markdown, no prose). Every item uses timestamp 0.0:\n"
        "[\n"
        "  {\n"
        '    "timestamp": 0.0,\n'
        '    "event_type": "scene_change",\n'
        '    "description": "detailed description, 20 to 40 words",\n'
        '    "confidence": 0.95,\n'
        '    "objects": ["object1", "object2", "object3"]\n'
        "  }\n"
        "]\n"
        "Produce 6 to 10 observations. Use these event_type values:\n"
        "- scene_change: overall scene, location/setting, time of day, weather, lighting, camera angle and composition.\n"
        "- action: each person or animal - appearance, clothing, expression, pose, what they are doing (one item per subject).\n"
        "- object_appears: notable objects, their position (foreground/background, left/right), colors, materials, condition.\n"
        "- speech: ALL visible text, signs, labels, logos, numbers - transcribe them exactly in quotes.\n"
        "- other: dominant colors and palette, mood/atmosphere, style (photo, illustration, screenshot), and any inferred context.\n"
        "Be specific and factual; list every relevant object in 'objects'. Do not invent details you cannot see."
    )

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{_encode_detail_image(image_path)}"
                    }
                }
            ]
        }
    ]

    effective_key = groq_api_key or settings.groq_api_key
    try:
        if effective_key:
            from groq import Groq
            client = Groq(api_key=effective_key)
            # Groq on_demand caps output at 1000 tokens/minute; 900 leaves headroom.
            raw = _call_groq_vision_with_backoff(
                client, messages, initial_tokens=900, min_tokens=600
            )
            events = _parse_events(raw, [{"timestamp": 0.0, "path": image_path}])
            if events:
                return events
    except Exception as e:
        print(f"[VisionService] Groq single image analysis failed: {e}")

    # Fallback to OpenCV analysis
    return _analyze_opencv([{"timestamp": 0.0, "path": image_path}])


def _encode_detail_image(image_path: str, max_side: int = 1600) -> str:
    """
    Re-encode any image (PNG/WEBP/BMP/huge JPEG) as a high-quality JPEG,
    capped at max_side px so fine details and text stay legible while the
    base64 payload stays under Groq's request size limit.
    """
    import cv2

    img = cv2.imread(image_path)
    if img is None:
        return _encode_image(image_path)
    h, w = img.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return base64.b64encode(buf.tobytes()).decode("utf-8")

