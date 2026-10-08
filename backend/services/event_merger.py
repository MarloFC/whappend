"""
Event merger.
Combines visual events and audio events into a unified, sorted timeline.
"""

from models.schemas import VisualEvent, AudioEvent, TimelineEvent, EventType
import uuid


def merge_events(
    visual_events: list[VisualEvent],
    audio_events: list[AudioEvent],
) -> list[TimelineEvent]:
    """
    Merge visual and audio events into a single sorted timeline.
    - Synchronizes timestamps precisely to whichever begins first (audio speech or visual action).
    - Prevents collapsing multiple distinct speech segments into one event.
    - Sets timestamp to min(visual, audio) so seeking never misses the beginning of speech.
    """
    timeline: list[TimelineEvent] = []

    # 1. Add all visual events
    for ve in visual_events:
        timeline.append(TimelineEvent(
            id=str(uuid.uuid4()),
            timestamp=round(float(ve.timestamp), 2),
            modality="visual",
            event_type=ve.event_type,
            description=ve.description,
            confidence=ve.confidence,
            raw_visual=ve,
        ))

    # 2. Add audio events — correlate with nearby unmerged visual event within tight 1.0s window
    for ae in audio_events:
        candidates = [
            e for e in timeline
            if e.raw_visual is not None and e.raw_audio is None and abs(e.timestamp - ae.timestamp) <= 1.0
        ]

        if candidates:
            # Associate with the closest visual event
            best = min(candidates, key=lambda e: abs(e.timestamp - ae.timestamp))
            best.modality = "merged"
            best.raw_audio = ae
            # Crucial: start timestamp aligns to whichever occurred first so seeking never cuts off speech
            best.timestamp = round(min(best.timestamp, ae.timestamp), 2)
            best.description = f"{best.description} | 🗣️ \"{ae.text}\""
        else:
            # Standalone audio event at its exact speech timestamp
            timeline.append(TimelineEvent(
                id=str(uuid.uuid4()),
                timestamp=round(float(ae.timestamp), 2),
                modality="audio",
                event_type=EventType.SPEECH,
                description=f"🗣️ \"{ae.text}\"",
                confidence=ae.confidence,
                raw_audio=ae,
            ))

    # 3. Sort strictly by timestamp
    timeline.sort(key=lambda e: e.timestamp)
    return timeline
