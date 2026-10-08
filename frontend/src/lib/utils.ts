import type { EventType } from "./types";

export function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function eventIcon(type: EventType): string {
  const icons: Record<EventType, string> = {
    person_enters: "👤",
    person_exits: "🚪",
    person_sits: "🪑",
    person_stands: "🧍",
    object_appears: "📦",
    object_removed: "📤",
    action: "⚡",
    speech: "🗣️",
    scene_change: "🎬",
    other: "🔷",
  };
  return icons[type] ?? "🔷";
}

export function eventTypeLabel(type: EventType): string {
  return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function statusColor(status: string): string {
  const map: Record<string, string> = {
    pending: "var(--color-warning)",
    processing: "var(--color-info)",
    completed: "var(--color-success)",
    failed: "var(--color-danger)",
  };
  return map[status] ?? "var(--color-muted)";
}
