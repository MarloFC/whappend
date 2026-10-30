"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import {
  Film,
  Loader2,
  CheckCircle,
  AlertCircle,
  ChevronRight,
  Key,
  BookOpen,
  ListTree,
  LogOut,
  Send,
  Globe,
} from "lucide-react";
import VideoUploader from "@/components/VideoUploader";
import MediaViewer, { resolveMediaType } from "@/components/MediaViewer";
import EventTimeline from "@/components/EventTimeline";
import ChaptersView from "@/components/ChaptersView";
import ChatPanel from "@/components/ChatPanel";
import ApiKeyModal from "@/components/ApiKeyModal";
import AuthModal from "@/components/AuthModal";
import {
  uploadVideo,
  getVideoStatus,
  getVideoEvents,
  getCurrentUser,
  clearAuthToken,
  listVideos,
  getMediaStreamUrl,
} from "@/lib/api";
import type {
  VideoStatus,
  TimelineEvent,
  MediaType,
  UserProfile,
  VideoStatusResponse,
} from "@/lib/types";

type AppState = "idle" | "uploading" | "processing" | "ready" | "error";

export default function Home() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [myLibrary, setMyLibrary] = useState<VideoStatusResponse[]>([]);

  const [appState, setAppState] = useState<AppState>("idle");
  const [videoId, setVideoId] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [mediaType, setMediaType] = useState<MediaType>("video");
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [, setStatus] = useState<VideoStatus>("pending");
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [activeTab, setActiveTab] = useState<"timeline" | "chapters">("timeline");
  const [activeEventId, setActiveEventId] = useState<string | undefined>();
  const [seekTo, setSeekTo] = useState<number | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [isKeyModalOpen, setIsKeyModalOpen] = useState(false);
  const [hasCustomKey, setHasCustomKey] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshLibrary = useCallback(async () => {
    try {
      const items = await listVideos();
      setMyLibrary(items);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    getCurrentUser()
      .then((u) => {
        setUser(u);
        if (u) {
          setHasCustomKey(u.has_groq_key);
          refreshLibrary();
        }
      })
      .finally(() => setAuthChecking(false));
  }, [refreshLibrary]);

  const stopPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
  };

  const startPolling = useCallback(
    (id: string) => {
      pollRef.current = setInterval(async () => {
        try {
          const s = await getVideoStatus(id);
          setStatus(s.status);

          if (s.status === "completed") {
            stopPolling();
            const evRes = await getVideoEvents(id);
            setEvents(evRes.events);
            setAppState("ready");
            refreshLibrary();
          } else if (s.status === "failed") {
            stopPolling();
            setError(s.error ?? "Processing failed.");
            setAppState("error");
            refreshLibrary();
          }
        } catch {
          // keep polling
        }
      }, 2500);
    },
    [refreshLibrary]
  );

  const handleUpload = useCallback(
    async (file: File) => {
      if (!hasCustomKey) {
        setIsKeyModalOpen(true);
        return;
      }

      setAppState("uploading");
      setVideoFile(file);
      setVideoUrl(URL.createObjectURL(file));
      setError(null);

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
    },
    [startPolling, hasCustomKey]
  );

  const handleSelectExistingMedia = useCallback(
    async (item: VideoStatusResponse) => {
      stopPolling();
      setError(null);
      setVideoFile(null);
      setVideoId(item.video_id);
      setMediaType((item.media_type as MediaType) || "video");
      setVideoUrl(getMediaStreamUrl(item.video_id));

      if (item.status === "completed") {
        try {
          const evRes = await getVideoEvents(item.video_id);
          setEvents(evRes.events);
          setAppState("ready");
        } catch (err) {
          setError(err instanceof Error ? err.message : "Failed to load media events.");
          setAppState("error");
        }
      } else if (item.status === "processing" || item.status === "pending") {
        setAppState("processing");
        startPolling(item.video_id);
      } else {
        setError(item.error ?? "Media processing failed.");
        setAppState("error");
      }
    },
    [startPolling]
  );

  const handleEventClick = useCallback((event: TimelineEvent) => {
    setActiveEventId(event.id);
    setSeekTo(Math.max(0, event.timestamp - 0.15));
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
    setActiveTab("timeline");
    refreshLibrary();
  };

  const handleLogout = () => {
    stopPolling();
    clearAuthToken();
    setUser(null);
    setMyLibrary([]);
    reset();
  };

  if (authChecking) {
    return (
      <main className="app">
        <div className="status-screen">
          <Loader2 size={32} className="animate-spin" />
        </div>
      </main>
    );
  }

  return (
    <main className="app">
      {/* ── Auth Gate ── */}
      {!user && (
        <AuthModal
          onAuthenticated={(loggedUser) => {
            setUser(loggedUser);
            setHasCustomKey(loggedUser.has_groq_key);
            refreshLibrary();
            if (!loggedUser.has_groq_key) {
              setIsKeyModalOpen(true);
            }
          }}
        />
      )}

      {/* ── Header ── */}
      <header className="app-header">
        <div className="app-header-inner">
          <div className="app-logo">
            <Film size={24} />
            <span>WhAppend</span>
          </div>
          <p className="app-tagline">Multimodal Intelligence: Video · Audio · Image · Telegram</p>
          <div className="header-actions">
            {user && (
              <>
                <span style={{ fontSize: "0.78rem", opacity: 0.75, marginRight: 4 }}>
                  {user.phone_e164}
                </span>
                <button
                  className={`btn btn-sm ${hasCustomKey ? "btn-key-active" : "btn-secondary"}`}
                  onClick={() => setIsKeyModalOpen(true)}
                  title="Configure your encrypted BYOK Groq API key"
                >
                  <Key size={14} />
                  <span>
                    {hasCustomKey
                      ? `Groq Key ${user.groq_key_last4 ? `(••${user.groq_key_last4})` : "Active"}`
                      : "Set BYOK Key"}
                  </span>
                </button>
              </>
            )}
            {appState !== "idle" && (
              <button className="btn btn-ghost btn-sm" onClick={reset}>
                ↩ Library / Upload
              </button>
            )}
            {user && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={handleLogout}
                title="Sign out"
              >
                <LogOut size={14} />
              </button>
            )}
          </div>
        </div>
      </header>

      {/* ── Content ── */}
      <div className="app-body">
        {/* IDLE: upload screen + recent Web & Telegram media library */}
        {appState === "idle" && (
          <div className="upload-screen">
            <div className="upload-hero">
              <h1 className="hero-title">
                Drop any media.<br />
                <span className="hero-accent">Understand everything.</span>
              </h1>
              <p className="hero-subtitle">
                AI-powered event detection and insights for Videos, Audio, and Images with your personal BYOK Groq key — synced across Web &amp; Telegram.
              </p>
            </div>
            <VideoUploader onUpload={handleUpload} isUploading={false} />

            {myLibrary.length > 0 && (
              <div style={{ width: "100%", maxWidth: 680, marginTop: 28 }}>
                <h3 style={{ fontSize: "0.9rem", opacity: 0.8, marginBottom: 10 }}>
                  Your Recent Media (Web &amp; Telegram)
                </h3>
                <div style={{ display: "grid", gap: 8 }}>
                  {myLibrary.slice(0, 8).map((item) => (
                    <button
                      key={item.video_id}
                      type="button"
                      onClick={() => handleSelectExistingMedia(item)}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        padding: "10px 14px",
                        borderRadius: 10,
                        background: "rgba(255,255,255,0.03)",
                        border: "1px solid rgba(255,255,255,0.08)",
                        cursor: "pointer",
                        textAlign: "left",
                        color: "inherit",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        {item.source === "telegram" ? <Send size={15} /> : <Globe size={15} />}
                        <div>
                          <div style={{ fontWeight: 500, fontSize: "0.88rem" }}>
                            {item.original_name || item.video_id}
                          </div>
                          <div style={{ fontSize: "0.75rem", opacity: 0.65 }}>
                            {item.media_type} · via {item.source || "web"} ·{" "}
                            {item.event_count ?? 0} events
                          </div>
                        </div>
                      </div>
                      <span style={{ fontSize: "0.78rem", opacity: 0.8 }}>{item.status}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
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
                <div className="workspace-tabs-header">
                  <div className="workspace-tabs">
                    <button
                      className={`workspace-tab ${activeTab === "timeline" ? "workspace-tab--active" : ""}`}
                      onClick={() => setActiveTab("timeline")}
                    >
                      <ListTree size={15} />
                      <span>Events ({events.length})</span>
                    </button>
                    <button
                      className={`workspace-tab ${activeTab === "chapters" ? "workspace-tab--active" : ""}`}
                      onClick={() => setActiveTab("chapters")}
                    >
                      <BookOpen size={15} />
                      <span>AI Chapters</span>
                    </button>
                  </div>
                  <div className="timeline-header-meta">
                    <CheckCircle size={14} className="text-success" />
                    <span>
                      {mediaType === "image"
                        ? "Visual metadata"
                        : mediaType === "audio"
                        ? "Speech transcribed"
                        : "Events indexed"}
                    </span>
                  </div>
                </div>

                {activeTab === "timeline" ? (
                  <EventTimeline
                    events={events}
                    activeEventId={activeEventId}
                    onEventClick={handleEventClick}
                    isStatic={mediaType === "image"}
                  />
                ) : (
                  <ChaptersView
                    videoId={videoId}
                    onSeek={(timestamp) => {
                      setSeekTo(Math.max(0, timestamp - 0.15));
                      setTimeout(() => setSeekTo(undefined), 100);
                    }}
                  />
                )}
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
        user={user}
        onKeyChange={(has, last4) => {
          setHasCustomKey(has);
          if (user) {
            setUser({ ...user, has_groq_key: has, groq_key_last4: last4 ?? null });
          }
        }}
      />
    </main>
  );
}
