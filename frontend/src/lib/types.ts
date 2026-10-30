// API types matching the FastAPI Pydantic schemas

export type VideoStatus = "pending" | "processing" | "completed" | "failed";

export type EventType =
  | "person_enters"
  | "person_exits"
  | "person_sits"
  | "person_stands"
  | "object_appears"
  | "object_removed"
  | "action"
  | "speech"
  | "scene_change"
  | "other";

export interface TimelineEvent {
  id: string;
  timestamp: number;
  modality: "visual" | "audio" | "merged";
  event_type: EventType;
  description: string;
  confidence: number;
}

export type MediaType = "video" | "audio" | "image";

export interface VideoUploadResponse {
  video_id: string;
  media_type?: MediaType;
  status: VideoStatus;
  message: string;
}

export interface VideoStatusResponse {
  video_id: string;
  original_name?: string | null;
  source?: "web" | "telegram" | string;
  media_type?: MediaType;
  status: VideoStatus;
  duration_seconds: number | null;
  frame_count: number | null;
  event_count: number | null;
  error: string | null;
}

export interface UserProfile {
  id: string;
  phone_e164: string;
  telegram_user_id?: number | null;
  telegram_username?: string | null;
  display_name?: string | null;
  role: "admin" | "user" | string;
  has_groq_key: boolean;
  groq_key_last4?: string | null;
  groq_key_validated_at?: string | null;
}

export interface AllowedUserItem {
  id: string;
  phone_e164: string;
  role: string;
  is_active: boolean;
  display_name?: string | null;
  telegram_user_id?: number | null;
  telegram_username?: string | null;
  has_groq_key: boolean;
  groq_key_last4?: string | null;
  created_at: string;
}

export interface EventsResponse {
  video_id: string;
  events: TimelineEvent[];
  total: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface Chapter {
  start_time: number;
  end_time: number;
  title: string;
  summary: string;
  key_topics: string[];
}

export interface ChaptersResponse {
  video_id: string;
  overview: string;
  chapters: Chapter[];
}

export interface QuestionResponse {
  answer: string;
  relevant_events: TimelineEvent[];
  video_id: string;
  used_agent?: boolean;
}
