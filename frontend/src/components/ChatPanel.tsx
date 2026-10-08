"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Loader2, Sparkles, MessageSquareQuote } from "lucide-react";
import type { TimelineEvent, QuestionResponse, MediaType } from "@/lib/types";
import { formatTimestamp, eventIcon } from "@/lib/utils";
import { askQuestion } from "@/lib/api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  relevantEvents?: TimelineEvent[];
}

interface Props {
  videoId: string;
  mediaType?: MediaType;
  onEventHighlight: (event: TimelineEvent) => void;
}

const generateId = () => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
};

export default function ChatPanel({ videoId, mediaType = "video", onEventHighlight }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const submit = async () => {
    const q = input.trim();
    if (!q || loading) return;

    const userMsg: Message = {
      id: generateId(),
      role: "user",
      content: q,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res: QuestionResponse = await askQuestion(videoId, q);
      const assistantMsg: Message = {
        id: generateId(),
        role: "assistant",
        content: res.answer,
        relevantEvents: res.relevant_events,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: generateId(),
          role: "assistant",
          content: "Sorry, could not answer this question right now. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <Sparkles size={16} />
        <span>
          {mediaType === "image"
            ? "Ask about this image"
            : mediaType === "audio"
            ? "Ask about this audio"
            : "Ask about this video"}
        </span>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <MessageSquareQuote size={32} className="chat-empty-icon" />
            <p>
              {mediaType === "image"
                ? "Ask anything about what is shown in this image, visible text, or detected objects."
                : mediaType === "audio"
                ? "Ask anything about what was spoken, topics discussed, or key points in this audio."
                : "Ask anything about what happened, who appeared, or what was said in the video."}
            </p>
            <div className="chat-suggestions">
              {(mediaType === "image"
                ? [
                    "What is shown in this image?",
                    "What text or labels are visible?",
                    "What objects and people are present?",
                  ]
                : mediaType === "audio"
                ? [
                    "What was said by the speaker?",
                    "What are the main topics discussed?",
                    "Can you summarize this recording?",
                  ]
                : [
                    "What happened in this video?",
                    "What was said by the speaker?",
                    "What objects or scenes were shown?",
                  ]
              ).map((s) => (
                <button
                  key={s}
                  className="chat-suggestion"
                  onClick={() => {
                    setInput(s);
                    inputRef.current?.focus();
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`chat-message chat-message--${msg.role}`}>
            <div className="chat-bubble">
              <p>{msg.content}</p>
            </div>
            {msg.relevantEvents && msg.relevantEvents.length > 0 && (
              <div className="chat-references">
                <span className="chat-references-label">Timestamp cues:</span>
                {msg.relevantEvents.map((ev) => (
                  <button
                    key={ev.id}
                    className="chat-reference-tag"
                    onClick={() => onEventHighlight(ev)}
                    title={`Jump to ${formatTimestamp(ev.timestamp)}`}
                  >
                    {eventIcon(ev.event_type)} {formatTimestamp(ev.timestamp)}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="chat-message chat-message--assistant">
            <div className="chat-bubble chat-bubble--loading">
              <Loader2 size={16} className="animate-spin" />
              <span>Analyzing timeline &amp; events…</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="chat-input-row">
        <input
          ref={inputRef}
          className="chat-input"
          placeholder={`Ask a question about the ${mediaType}...`}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          disabled={loading}
          autoComplete="off"
          data-lpignore="true"
          data-form-type="other"
        />
        <button
          className="btn btn-primary btn-icon"
          onClick={submit}
          disabled={loading || !input.trim()}
          aria-label="Send question"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
