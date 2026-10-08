"use client";

import { useState, useEffect } from "react";
import { BookOpen, Play, Loader2, Sparkles, Tag, RotateCw } from "lucide-react";
import type { Chapter, ChaptersResponse } from "@/lib/types";
import { formatTimestamp } from "@/lib/utils";
import { getVideoChapters } from "@/lib/api";

interface Props {
  videoId: string;
  onSeek: (seconds: number) => void;
}

export default function ChaptersView({ videoId, onSeek }: Props) {
  const [data, setData] = useState<ChaptersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchChapters = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getVideoChapters(videoId);
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate AI chapters.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (videoId) {
      fetchChapters();
    }
  }, [videoId]);

  if (loading) {
    return (
      <div className="chapters-loading">
        <Loader2 size={24} className="animate-spin text-accent" />
        <p>LangChain synthesizing video chapters &amp; topics…</p>
      </div>
    );
  }

  if (error || !data || data.chapters.length === 0) {
    return (
      <div className="chapters-empty">
        <BookOpen size={28} className="text-muted" />
        <p>{error || "No chapters generated for this media."}</p>
        <button className="btn btn-secondary btn-sm" onClick={fetchChapters}>
          <RotateCw size={13} /> Try Again
        </button>
      </div>
    );
  }

  return (
    <div className="chapters-view">
      {/* Overview Banner */}
      {data.overview && (
        <div className="chapters-overview-card">
          <div className="chapters-overview-header">
            <Sparkles size={15} className="text-accent" />
            <span className="chapters-overview-title">AI Video Synthesis</span>
          </div>
          <p className="chapters-overview-text">{data.overview}</p>
        </div>
      )}

      {/* Chapter List */}
      <div className="chapters-list">
        {data.chapters.map((ch, idx) => (
          <div
            key={idx}
            className="chapter-card"
            onClick={() => onSeek(ch.start_time)}
            title={`Jump to ${formatTimestamp(ch.start_time)}`}
          >
            <div className="chapter-header">
              <div className="chapter-time-badge">
                <Play size={11} className="chapter-play-icon" />
                <span>
                  {formatTimestamp(ch.start_time)} - {formatTimestamp(ch.end_time)}
                </span>
              </div>
              <span className="chapter-number">Chapter {idx + 1}</span>
            </div>

            <h3 className="chapter-title">{ch.title}</h3>
            <p className="chapter-summary">{ch.summary}</p>

            {ch.key_topics && ch.key_topics.length > 0 && (
              <div className="chapter-topics">
                {ch.key_topics.map((topic, tIdx) => (
                  <span key={tIdx} className="chapter-topic-pill">
                    <Tag size={10} />
                    {topic}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
