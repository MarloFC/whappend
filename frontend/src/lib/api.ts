import type {
  VideoUploadResponse,
  VideoStatusResponse,
  EventsResponse,
  QuestionResponse,
  ChaptersResponse,
  ChatMessage,
  UserProfile,
  AllowedUserItem,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_STORAGE_KEY = "whappend_auth_token";
const LEGACY_API_KEY = "whappend_groq_api_key";

// ─── JWT Session Token Storage ──────────────────────────────────────────────

export function getAuthToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(TOKEN_STORAGE_KEY) || "";
}

export function setAuthToken(token: string): void {
  if (typeof window === "undefined") return;
  const trimmed = token.trim();
  if (trimmed) {
    localStorage.setItem(TOKEN_STORAGE_KEY, trimmed);
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

export function clearAuthToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_STORAGE_KEY);
}

// Legacy helpers kept for compatibility
export function getStoredApiKey(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(LEGACY_API_KEY) || "";
}

export function setStoredApiKey(key: string): void {
  if (typeof window === "undefined") return;
  if (key.trim()) localStorage.setItem(LEGACY_API_KEY, key.trim());
  else localStorage.removeItem(LEGACY_API_KEY);
}

export function clearStoredApiKey(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(LEGACY_API_KEY);
}

function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = getAuthToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const legacyKey = getStoredApiKey();
  if (legacyKey) {
    headers["X-Groq-Api-Key"] = legacyKey;
  }
  return headers;
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    return JSON.stringify(data);
  } catch {
    return await res.text();
  }
}

// ─── Authentication (Phone + Bot OTP & Telegram Login Widget) ────────────────

export interface OtpRequestResponse {
  sent: boolean;
  phone_e164: string;
  delivery: "telegram" | "dev_console" | string;
  message: string;
  dev_code?: string | null;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  user: UserProfile;
}

export async function requestPhoneOtp(phone: string): Promise<OtpRequestResponse> {
  const res = await fetch(`${BASE}/auth/otp/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function verifyPhoneOtp(phone: string, code: string): Promise<AuthTokenResponse> {
  const res = await fetch(`${BASE}/auth/otp/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, code }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data: AuthTokenResponse = await res.json();
  setAuthToken(data.access_token);
  return data;
}

export interface TelegramWidgetUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
}

export async function loginWithTelegramWidget(payload: TelegramWidgetUser): Promise<AuthTokenResponse> {
  const res = await fetch(`${BASE}/auth/telegram-widget`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data: AuthTokenResponse = await res.json();
  setAuthToken(data.access_token);
  return data;
}

export async function getCurrentUser(): Promise<UserProfile | null> {
  const token = getAuthToken();
  if (!token) return null;
  try {
    const res = await fetch(`${BASE}/auth/me`, {
      headers: getAuthHeaders(),
    });
    if (!res.ok) {
      if (res.status === 401 || res.status === 403) clearAuthToken();
      return null;
    }
    return res.json();
  } catch {
    return null;
  }
}

// ─── Encrypted BYOK Groq Key Management (`/me/groq-key`) ─────────────────────

export interface GroqKeyStatus {
  configured: boolean;
  provider: string;
  masked_key?: string | null;
  key_last4?: string | null;
  validated_at?: string | null;
  message?: string | null;
}

export async function getMyGroqKeyStatus(): Promise<GroqKeyStatus> {
  const res = await fetch(`${BASE}/me/groq-key`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function saveMyGroqKey(apiKey: string): Promise<GroqKeyStatus> {
  const res = await fetch(`${BASE}/me/groq-key`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function deleteMyGroqKey(): Promise<GroqKeyStatus> {
  const res = await fetch(`${BASE}/me/groq-key`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

// ─── Admin Allowlist Management (`/admin/users`) ────────────────────────────

export async function listAllowedUsers(): Promise<AllowedUserItem[]> {
  const res = await fetch(`${BASE}/admin/users`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function addAllowedUser(
  phone: string,
  role: "user" | "admin" = "user",
  displayName?: string
): Promise<AllowedUserItem> {
  const res = await fetch(`${BASE}/admin/users`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ phone, role, display_name: displayName, is_active: true }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function removeAllowedUser(phone: string): Promise<void> {
  const res = await fetch(`${BASE}/admin/users/${encodeURIComponent(phone)}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
}

// ─── Server Config Status ───────────────────────────────────────────────────

export interface KeyStatusResponse {
  has_server_key: boolean;
  byok_required?: boolean;
  provider: string;
  vision_model: string;
  llm_model: string;
  telegram_enabled?: boolean;
}

export async function getKeyStatus(): Promise<KeyStatusResponse> {
  try {
    const res = await fetch(`${BASE}/config/key-status`);
    if (!res.ok) throw new Error("Failed to check server key status");
    return res.json();
  } catch {
    return {
      has_server_key: false,
      byok_required: true,
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

// ─── Videos / Media ──────────────────────────────────────────────────────────

export function getMediaStreamUrl(videoId: string): string {
  const token = getAuthToken();
  const qs = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${BASE}/videos/${videoId}/media${qs}`;
}

export async function uploadVideo(file: File): Promise<VideoUploadResponse> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${BASE}/videos`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: form,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getVideoStatus(videoId: string): Promise<VideoStatusResponse> {
  const res = await fetch(`${BASE}/videos/${videoId}/status`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getVideoEvents(videoId: string): Promise<EventsResponse> {
  const res = await fetch(`${BASE}/videos/${videoId}/events`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listVideos(): Promise<VideoStatusResponse[]> {
  const res = await fetch(`${BASE}/videos`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

// ─── Ask ─────────────────────────────────────────────────────────────────────

export async function askQuestion(
  videoId: string,
  question: string,
  history?: ChatMessage[],
  useAgent: boolean = false,
): Promise<QuestionResponse> {
  const res = await fetch(`${BASE}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify({
      video_id: videoId,
      question,
      history,
      use_agent: useAgent,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

// ─── Chapters (LangChain Structured Output) ──────────────────────────────────

export async function getVideoChapters(videoId: string): Promise<ChaptersResponse> {
  const res = await fetch(`${BASE}/videos/${videoId}/chapters`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
