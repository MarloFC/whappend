"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { Film, Loader2, CheckCircle, AlertCircle, ChevronRight, Key } from "lucide-react";
import VideoUploader from "@/components/VideoUploader";
import MediaViewer, { resolveMediaType } from "@/components/MediaViewer";
import EventTimeline from "@/components/EventTimeline";
import ChatPanel from "@/components/ChatPanel";
import ApiKeyModal from "@/components/ApiKeyModal";
import { uploadVideo, getVideoStatus, getVideoEvents, getStoredApiKey } from "@/lib/api";
import type { VideoStatus, TimelineEvent, MediaType } from "@/lib/types";

type AppState = "idle" | "uploading" | "processing" | "ready" | "error";

export default function Home() {
  const [appState, setAppState] = useState<AppState>("idle");
  const [videoId, setVideoId] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [mediaType, setMediaType] = useState<MediaType>("video");
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [, setStatus] = useState<VideoStatus>("pending");
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [activeEventId, setActiveEventId] = useState<string | undefined>();
  const [seekTo, setSeekTo] = useState<number | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [isKeyModalOpen, setIsKeyModalOpen] = useState(false);
  const [hasCustomKey, setHasCustomKey] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setHasCustomKey(Boolean(getStoredApiKey()));
  }, []);

  const stopPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
  };

  const startPolling = useCallback((id: string) => {
    pollRef.current = setInterval(async () => {
      try {
        const s = await getVideoStatus(id);
        setStatus(s.status);

        if (s.status === "completed") {
          stopPolling();
          const evRes = await getVideoEvents(id);
          setEvents(evRes.events);
          setAppState("ready");
        } else if (s.status === "failed") {
          stopPolling();
          setError(s.error ?? "Processing failed.");
          setAppState("error");
        }
      } catch {
        // keep polling
      }
    }, 2500);
  }, []);

  const handleUpload = useCallback(async (file: File) => {
    setAppState("uploading");
    setVideoFile(file);
    setVideoUrl(URL.createObjectURL(file));
    setError(null);

    // The local file is the source of truth for the media kind
    const localType = resolveMediaType(file, "video");
    setMediaType(localType);

    try {
      const res = await uploadVideo(file);
      setVideoId(res.video_id);
      setAppState("processing");
      setStatus("processing");
      startPolling(res.video_id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed.");
      setAppState("error");
    }
  }, [startPolling]);

  const handleEventClick = useCallback((event: TimelineEvent) => {
    setActiveEventId(event.id);
    // Subtle 150ms lead-in buffer so speech starts from the first syllable
    setSeekTo(Math.max(0, event.timestamp - 0.15));
    // Reset seekTo after a tick so clicking the same timestamp can re-trigger
    setTimeout(() => setSeekTo(undefined), 100);
  }, []);

  const reset = () => {
    stopPolling();
    setAppState("idle");
    setVideoId(null);
    setVideoUrl(null);
    setMediaType("video");
    setVideoFile(null);
    setEvents([]);
    setActiveEventId(undefined);
    setError(null);
  };

  return (
    <main className="app">
      {/* ── Header ── */}
      <header className="app-header">
        <div className="app-header-inner">
          <div className="app-logo">
            <Film size={24} />
            <span>WhAppend</span>
          </div>
          <p className="app-tagline">Multimodal Intelligence: Video · Audio · Image</p>
          <div className="header-actions">
            <button
              className={`btn btn-sm ${hasCustomKey ? "btn-key-active" : "btn-secondary"}`}
              onClick={() => setIsKeyModalOpen(true)}
              title="Configure Groq API Key (BYOK)"
            >
              <Key size={14} />
              <span>{hasCustomKey ? "Custom Key Active" : "API Key"}</span>
            </button>
            {appState !== "idle" && (
              <button className="btn btn-ghost btn-sm" onClick={reset}>
                ↩ New Media
              </button>
            )}
          </div>
        </div>
      </header>

      {/* ── Content ── */}
      <div className="app-body">
        {/* IDLE: upload screen */}
        {appState === "idle" && (
          <div className="upload-screen">
            <div className="upload-hero">
              <h1 className="hero-title">
                Drop any media.<br />
                <span className="hero-accent">Understand everything.</span>
              </h1>
              <p className="hero-subtitle">
                AI-powered event detection and insights for Videos, Audio, and Images with Groq &amp; RAG Q&amp;A.
              </p>
            </div>
            <VideoUploader onUpload={handleUpload} isUploading={false} />
          </div>
        )}

        {/* UPLOADING */}
        {appState === "uploading" && (
          <div className="status-screen">
            <VideoUploader onUpload={handleUpload} isUploading={true} />
          </div>
        )}

        {/* PROCESSING */}
        {appState === "processing" && (
          <div className="status-screen">
            <div className="processing-card">
              <div className="processing-icon">
                <Loader2 size={36} className="animate-spin" />
              </div>
              <h2 className="processing-title">
                Analyzing your {mediaType}…
              </h2>
              <div className="processing-steps">
                {(mediaType === "image"
                  ? [
                      { label: "Image uploaded & validated", done: true },
                      { label: "Vision model analyzing scene & objects", done: false },
                      { label: "Extracting visual metadata & OCR", done: false },
                      { label: "Indexing for RAG Q&A", done: false },
                    ]
                  : mediaType === "audio"
                  ? [
                      { label: "Audio track extracted", done: true },
                      { label: "Groq Whisper speech transcription", done: false },
                      { label: "Timestamp alignment & speaker cues", done: false },
                      { label: "Indexing for RAG Q&A", done: false },
                    ]
                  : [
                      { label: "Frames extracted", done: true },
                      { label: "Vision model analyzing collage frames", done: false },
                      { label: "Audio transcription (Groq Whisper)", done: false },
                      { label: "Building event timeline", done: false },
                      { label: "Indexing for RAG Q&A", done: false },
                    ]
                ).map((step, i) => (
                  <div key={i} className={`processing-step ${step.done ? "done" : ""}`}>
                    <ChevronRight size={14} />
                    <span>{step.label}</span>
                  </div>
                ))}
              </div>
              <p className="processing-note">
                {mediaType === "image"
                  ? "Image intelligence takes ~3–8 seconds."
                  : "Audio & video analysis takes ~10–35 seconds."}
              </p>
            </div>
          </div>
        )}

        {/* ERROR */}
        {appState === "error" && (
          <div className="status-screen">
            <div className="error-card">
              <AlertCircle size={40} />
              <h2>Something went wrong</h2>
              <p>{error}</p>
              <button className="btn btn-primary" onClick={reset}>Try Again</button>
            </div>
          </div>
        )}

        {/* READY: main workspace */}
        {appState === "ready" && videoId && videoUrl && (
          <div className="workspace">
            {/* Left: player/viewer + timeline */}
            <div className="workspace-left">
              <MediaViewer
                src={videoUrl}
                file={videoFile}
                mediaType={mediaType}
                seekTo={seekTo}
                onTimeUpdate={(t) => {
                  if (events.length === 0) return;
                  const current = events
                    .filter((e) => e.timestamp <= t + 0.15)
                    .slice(-1)[0];
                  if (current && current.id !== activeEventId) {
                    setActiveEventId(current.id);
                  }
                }}
              />
              <div className="timeline-container">
                <div className="timeline-header">
                  <CheckCircle size={16} className="text-success" />
                  <span>
                    {events.length}{" "}
                    {mediaType === "image"
                      ? "visual elements extracted"
                      : mediaType === "audio"
                      ? "speech segments transcribed"
                      : "timeline events detected"}
                  </span>
                </div>
                <EventTimeline
                  events={events}
                  activeEventId={activeEventId}
                  onEventClick={handleEventClick}
                  isStatic={mediaType === "image"}
                />
              </div>
            </div>

            {/* Right: chat */}
            <div className="workspace-right">
              <ChatPanel
                videoId={videoId}
                mediaType={mediaType}
                onEventHighlight={handleEventClick}
              />
            </div>
          </div>
        )}
      </div>
      <ApiKeyModal
        isOpen={isKeyModalOpen}
        onClose={() => setIsKeyModalOpen(false)}
        onKeyChange={(has) => setHasCustomKey(has)}
      />
    </main>
  );
}
