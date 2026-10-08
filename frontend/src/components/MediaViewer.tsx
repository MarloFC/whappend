"use client";

import { useRef, useEffect, useCallback, useState } from "react";
import { Mic, Image as ImageIcon, Volume2 } from "lucide-react";
import type { MediaType } from "@/lib/types";

interface Props {
  src: string;
  mediaType?: MediaType;
  /** Original File, used as a fallback to detect the media kind from its MIME/extension */
  file?: File | null;
  seekTo?: number;
  onTimeUpdate?: (currentTime: number) => void;
}

const IMAGE_EXTS = ["jpg", "jpeg", "png", "webp", "bmp", "gif", "tiff"];
const AUDIO_EXTS = ["mp3", "wav", "m4a", "ogg", "flac", "aac", "wma"];

/** Resolve the media kind: the local File wins (it is the ground truth), then the backend value. */
export function resolveMediaType(file?: File | null, fallback: MediaType = "video"): MediaType {
  if (file) {
    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (file.type.startsWith("image/") || IMAGE_EXTS.includes(ext)) return "image";
    if (file.type.startsWith("audio/") || AUDIO_EXTS.includes(ext)) return "audio";
    if (file.type.startsWith("video/")) return "video";
  }
  return fallback;
}

export default function MediaViewer({ src, mediaType, file, seekTo, onTimeUpdate }: Props) {
  const kind = resolveMediaType(file, mediaType ?? "video");
  const videoRef = useRef<HTMLVideoElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [imgError, setImgError] = useState(false);

  // Seek video/audio when the parent requests it (no-op for images)
  useEffect(() => {
    if (seekTo === undefined) return;
    const el = kind === "video" ? videoRef.current : kind === "audio" ? audioRef.current : null;
    if (el) {
      el.currentTime = seekTo;
      el.play().catch(() => {});
    }
  }, [seekTo, kind]);

  const handleTimeUpdate = useCallback(
    (e: React.SyntheticEvent<HTMLMediaElement>) => {
      onTimeUpdate?.(e.currentTarget.currentTime);
    },
    [onTimeUpdate]
  );

  // ── IMAGE ──────────────────────────────────────────────────────────────────
  if (kind === "image") {
    return (
      <div className="media-viewer media-viewer--image">
        <div className="image-viewer-container">
          {imgError ? (
            <p className="image-viewer-error">Could not display this image preview.</p>
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={src}
              alt={file?.name ?? "Uploaded image"}
              className="image-viewer-element"
              onError={() => setImgError(true)}
            />
          )}
          <div className="image-viewer-badge">
            <ImageIcon size={14} />
            <span>Analyzed Image</span>
          </div>
        </div>
      </div>
    );
  }

  // ── AUDIO ──────────────────────────────────────────────────────────────────
  if (kind === "audio") {
    return (
      <div className="media-viewer media-viewer--audio">
        <div className="audio-card">
          <div className="audio-card-header">
            <div className="audio-visualizer-icon">
              <Mic size={24} />
            </div>
            <div className="audio-card-meta">
              <span className="audio-card-title">{file?.name ?? "Audio Track & Speech"}</span>
              <span className="audio-card-subtitle">Transcribed via Groq Whisper</span>
            </div>
            <div className="audio-status-pill">
              <Volume2 size={13} />
              <span>{isPlaying ? "Playing" : "Paused"}</span>
            </div>
          </div>

          <div className={`audio-waveform ${isPlaying ? "audio-waveform--active" : ""}`}>
            {[40, 65, 85, 45, 95, 70, 30, 85, 60, 90, 50, 75, 95, 40, 60, 80, 55, 90, 65, 40].map((h, i) => (
              <span
                key={i}
                className="waveform-bar"
                style={{ height: `${isPlaying ? h : h * 0.4}%`, animationDelay: `${i * 0.06}s` }}
              />
            ))}
          </div>

          <audio
            ref={audioRef}
            src={src}
            controls
            className="audio-element"
            onTimeUpdate={handleTimeUpdate}
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
          />
        </div>
      </div>
    );
  }

  // ── VIDEO ──────────────────────────────────────────────────────────────────
  return (
    <div className="video-player">
      <video
        ref={videoRef}
        src={src}
        controls
        className="video-element"
        onTimeUpdate={handleTimeUpdate}
        playsInline
      />
    </div>
  );
}
