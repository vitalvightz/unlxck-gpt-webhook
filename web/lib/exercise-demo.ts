/**
 * Exercise demo video helpers: URLs, the watched-once memory, and a single
 * shared loader for the YouTube IFrame Player API.
 *
 * Videos come from the server (`outputs.exercise_media`), never from the plan
 * text or the model, so every ID here was curated and oEmbed-checked.
 */
import type { ExerciseMedia } from "@/lib/types";

export const YOUTUBE_NOCOOKIE_HOST = "https://www.youtube-nocookie.com";

export function demoThumbnailUrl(videoId: string, size: "mq" | "hq" = "hq"): string {
  return `https://i.ytimg.com/vi/${encodeURIComponent(videoId)}/${size}default.jpg`;
}

/** Full video on YouTube, opened at the start of the demo segment. */
export function demoFullVideoUrl(media: ExerciseMedia): string {
  const start = Math.max(0, Math.floor(media.start_s || 0));
  const params = new URLSearchParams({ v: media.video_id });
  if (start > 0) params.set("t", `${start}s`);
  return `https://www.youtube.com/watch?${params.toString()}`;
}

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/** "0:42–1:10" for a bounded segment, "from 0:42" for an open one. */
export function demoSegmentLabel(media: ExerciseMedia): string | null {
  const start = Math.max(0, media.start_s || 0);
  const end = media.end_s ?? null;
  if (end != null && end > start) return `${clock(start)}–${clock(end)}`;
  return start > 0 ? `from ${clock(start)}` : null;
}

// ---------------------------------------------------------------------------
// Watched-once memory. After the first view the demo steps back to a compact
// "Replay demo" strip so experienced athletes lead with the cues. Keyed by
// video, so swapping an exercise's video shows the new one in full again.
// Per-device and best-effort: storage can be unavailable (private mode).
// ---------------------------------------------------------------------------

const WATCHED_STORAGE_KEY = "unlxck:demo-watched:v1";
const WATCHED_EVENT = "unlxck:demo-watched";
const WATCHED_LIMIT = 500;

function readWatched(): string[] {
  try {
    const raw = window.localStorage.getItem(WATCHED_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

export function hasWatchedDemo(videoId: string): boolean {
  if (typeof window === "undefined") return false;
  return readWatched().includes(videoId);
}

export function markDemoWatched(videoId: string): void {
  if (typeof window === "undefined") return;
  try {
    const next = [videoId, ...readWatched().filter((id) => id !== videoId)].slice(0, WATCHED_LIMIT);
    window.localStorage.setItem(WATCHED_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Storage full or blocked: the demo just stays in its first-view layout.
    return;
  }
  if (typeof window.dispatchEvent === "function") {
    window.dispatchEvent(new Event(WATCHED_EVENT));
  }
}

/** useSyncExternalStore subscription: this tab's marks and other tabs' writes. */
export function subscribeDemoWatched(onChange: () => void): () => void {
  if (typeof window === "undefined" || typeof window.addEventListener !== "function") {
    return () => {};
  }
  window.addEventListener(WATCHED_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(WATCHED_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

// ---------------------------------------------------------------------------
// YouTube IFrame Player API (https://developers.google.com/youtube/iframe_api_reference)
// Loaded once, on the first tap of any demo — never on page load.
// ---------------------------------------------------------------------------

export type YouTubePlayer = {
  playVideo(): void;
  pauseVideo(): void;
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  mute(): void;
  unMute(): void;
  setPlaybackRate(rate: number): void;
  getCurrentTime(): number;
  destroy(): void;
};

export type YouTubePlayerEvent = { target: YouTubePlayer; data?: number };

export type YouTubeNamespace = {
  Player: new (
    element: HTMLElement,
    options: {
      host?: string;
      videoId: string;
      width?: string | number;
      height?: string | number;
      playerVars?: Record<string, string | number>;
      events?: {
        onReady?: (event: YouTubePlayerEvent) => void;
        onStateChange?: (event: YouTubePlayerEvent) => void;
        onError?: (event: YouTubePlayerEvent) => void;
      };
    },
  ) => YouTubePlayer;
  PlayerState: { ENDED: number; PLAYING: number; PAUSED: number };
};

type YouTubeWindow = Window & {
  YT?: YouTubeNamespace;
  onYouTubeIframeAPIReady?: () => void;
};

const IFRAME_API_SRC = "https://www.youtube.com/iframe_api";
const IFRAME_API_TIMEOUT_MS = 15000;
let iframeApiPromise: Promise<YouTubeNamespace> | null = null;

export function loadYouTubeIframeApi(): Promise<YouTubeNamespace> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("YouTube player needs a browser"));
  }
  const win = window as YouTubeWindow;
  if (win.YT?.Player) return Promise.resolve(win.YT);
  if (iframeApiPromise) return iframeApiPromise;

  iframeApiPromise = new Promise<YouTubeNamespace>((resolve, reject) => {
    const previous = win.onYouTubeIframeAPIReady;
    const script = document.createElement("script");
    // Every failure clears the cached promise and hands the global hook back,
    // so the next tap retries from scratch instead of reusing a rejection.
    const fail = (message: string) => {
      window.clearTimeout(timer);
      iframeApiPromise = null;
      win.onYouTubeIframeAPIReady = previous;
      script.remove();
      reject(new Error(message));
    };
    const timer = window.setTimeout(() => fail("YouTube player timed out"), IFRAME_API_TIMEOUT_MS);
    win.onYouTubeIframeAPIReady = () => {
      previous?.();
      if (win.YT?.Player) {
        window.clearTimeout(timer);
        resolve(win.YT);
      } else {
        fail("YouTube player failed to load");
      }
    };
    script.src = IFRAME_API_SRC;
    script.async = true;
    script.onerror = () => fail("YouTube player failed to load");
    document.head.appendChild(script);
  });
  return iframeApiPromise;
}
