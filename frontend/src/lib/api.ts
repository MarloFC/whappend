import type {
  VideoUploadResponse,
  VideoStatusResponse,
  EventsResponse,
  QuestionResponse,
  ChaptersResponse,
  ChatMessage,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STORAGE_KEY = "whappend_groq_api_key";

// ─── API Key Local Storage Helpers ──────────────────────────────────────────

export function getStoredApiKey(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(STORAGE_KEY) || "";
}

export function setStoredApiKey(key: string): void {
  if (typeof window === "undefined") return;
  const trimmed = key.trim();
  if (trimmed) {
    localStorage.setItem(STORAGE_KEY, trimmed);
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

export function clearStoredApiKey(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(STORAGE_KEY);
}

function getAuthHeaders(): Record<string, string> {
  const key = getStoredApiKey();
  if (key) {
    return { "X-Groq-Api-Key": key };
  }
  return {};
}

// ─── Key Status & Validation ────────────────────────────────────────────────

export interface KeyStatusResponse {
  has_server_key: boolean;
  provider: string;
  vision_model: string;
  llm_model: string;
}

export async function getKeyStatus(): Promise<KeyStatusResponse> {
  try {
    const res = await fetch(`${BASE}/config/key-status`);
    if (!res.ok) throw new Error("Failed to check server key status");
    return res.json();
  } catch {
    return {
      has_server_key: false,
      provider: "groq",
      vision_model: "qwen/qwen3.8-27b",
      llm_model: "qwen/qwen3.8-27b",
    };
  }
}

export async function validateApiKey(apiKey: string): Promise<{ valid: boolean; message?: string; error?: string }> {
  try {
    const res = await fetch(`${BASE}/auth/validate-key`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey }),
    });
    return res.json();
  } catch (err) {
    return { valid: false, error: err instanceof Error ? err.message : "Validation failed." };
  }
}

// ─── Videos ───────────────────────────────────────────────────────────────────

export async function uploadVideo(file: File): Promise<VideoUploadResponse> {
  const form = new FormData();
  form.append("file", file);

  const authHeaders = getAuthHeaders();
  const res = await fetch(`${BASE}/videos`, {
    method: "POST",
    headers: {
      ...authHeaders,
    },
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getVideoStatus(
  videoId: string
): Promise<VideoStatusResponse> {
  const res = await fetch(`${BASE}/videos/${videoId}/status`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getVideoEvents(
  videoId: string
): Promise<EventsResponse> {
  const res = await fetch(`${BASE}/videos/${videoId}/events`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listVideos(): Promise<VideoStatusResponse[]> {
  const res = await fetch(`${BASE}/videos`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ─── Ask ──────────────────────────────────────────────────────────────────────

export async function askQuestion(
  videoId: string,
  question: string,
  history?: ChatMessage[],
  useAgent: boolean = false,
): Promise<QuestionResponse> {
  const authHeaders = getAuthHeaders();
  const res = await fetch(`${BASE}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
    },
    body: JSON.stringify({
      video_id: videoId,
      question,
      history,
      use_agent: useAgent,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ─── Chapters (LangChain Structured Output) ──────────────────────────────────

export async function getVideoChapters(videoId: string): Promise<ChaptersResponse> {
  const authHeaders = getAuthHeaders();
  const res = await fetch(`${BASE}/videos/${videoId}/chapters`, {
    headers: {
      ...authHeaders,
    },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
