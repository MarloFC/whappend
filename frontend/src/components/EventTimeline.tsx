"use client";

import { useEffect, useRef } from "react";
import { Play, Volume2, Eye, Sparkles } from "lucide-react";
import type { TimelineEvent } from "@/lib/types";
import { formatTimestamp, eventIcon, eventTypeLabel } from "@/lib/utils";

interface Props {
  events: TimelineEvent[];
  activeEventId?: string;
  onEventClick: (event: TimelineEvent) => void;
  /** Images have no time axis: hide timestamps/play badges */
  isStatic?: boolean;
}

const IMAGE_LABELS: Record<string, string> = {
  scene_change: "Scene",
  action: "People & Actions",
  object_appears: "Objects",
  speech: "Visible Text",
  other: "Detail",
};

export default function EventTimeline({ events, activeEventId, onEventClick, isStatic = false }: Props) {
  const activeRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [activeEventId]);

  if (events.length === 0) {
    return (
      <div className="timeline-empty">
        <p>No events detected yet.</p>
      </div>
    );
  }

  return (
    <div className="timeline">
      <div className="timeline-track">
        {events.map((event) => {
          const isActive = event.id === activeEventId;

          // Parse description into visual action vs spoken speech if merged
          let visualPart = event.description;
          let speechParts: string[] = [];

          if (event.description.includes(" | 🗣️ ")) {
            const pieces = event.description.split(" | 🗣️ ");
            visualPart = pieces[0];
            speechParts = pieces.slice(1).map((s) => s.replace(/^"|"$/g, "").trim());
          } else if (event.modality === "audio") {
            visualPart = "";
            speechParts = [event.description.replace(/^🗣️\s*"?|"?$/g, "").trim()];
          }

          return (
            <button
              key={event.id}
              ref={isActive ? activeRef : null}
              className={`timeline-event ${isActive ? "timeline-event--active" : ""} timeline-event--${event.modality}`}
              onClick={() => onEventClick(event)}
              title={isStatic ? undefined : `Jump to ${formatTimestamp(event.timestamp)}`}
            >
              {/* Left icon marker */}
              <div className="timeline-event-marker">
                <span className="timeline-event-icon">{eventIcon(event.event_type)}</span>
              </div>

              {/* Event Body */}
              <div className="timeline-event-content">
                {/* Header row */}
                <div className="timeline-event-header">
                  {!isStatic && (
                    <div className="timeline-event-time-badge">
                      <Play size={11} className="time-play-icon" />
                      <span className="timeline-event-time">
                        {formatTimestamp(event.timestamp)}
                      </span>
                    </div>
                  )}

                  <span className="timeline-event-type">
                    {isStatic
                      ? IMAGE_LABELS[event.event_type] ?? eventTypeLabel(event.event_type)
                      : eventTypeLabel(event.event_type)}
                  </span>

                  {/* Modality Tag (only meaningful for time-based media) */}
                  {!isStatic && event.modality === "merged" && (
                    <span className="modality-tag modality-tag--merged">
                      <Sparkles size={11} /> Merged
                    </span>
                  )}
                  {!isStatic && event.modality === "visual" && (
                    <span className="modality-tag modality-tag--visual">
                      <Eye size={11} /> Visual
                    </span>
                  )}
                  {!isStatic && event.modality === "audio" && (
                    <span className="modality-tag modality-tag--audio">
                      <Volume2 size={11} /> Speech
                    </span>
                  )}

                  <span className="timeline-event-confidence">
                    {Math.round(event.confidence * 100)}%
                  </span>
                </div>

                {/* Visual action text */}
                {visualPart && (
                  <p className="timeline-event-visual-text">{visualPart}</p>
                )}

                {/* Spoken dialogue text */}
                {speechParts.length > 0 && (
                  <div className="timeline-event-speech-list">
                    {speechParts.map((sp, idx) => (
                      <div key={idx} className="timeline-event-speech-bubble">
                        <Volume2 size={13} className="speech-bubble-icon" />
                        <span className="speech-quote">&ldquo;{sp}&rdquo;</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
