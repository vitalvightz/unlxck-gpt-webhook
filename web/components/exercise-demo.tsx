"use client";

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import {
  YOUTUBE_NOCOOKIE_HOST,
  demoFullVideoUrl,
  demoSegmentLabel,
  demoThumbnailUrl,
  hasWatchedDemo,
  loadYouTubeIframeApi,
  markDemoWatched,
  subscribeDemoWatched,
  type YouTubePlayer,
} from "@/lib/exercise-demo";
import type { ExerciseMedia } from "@/lib/types";

// ---------------------------------------------------------------------------
// Plan-level media map, relayed to the exercise rows like the rehab label
// policy: Plan Detail mounts it through StructuredPlanRenderer, Today mounts it
// around its standalone SessionCards.
// ---------------------------------------------------------------------------

const ExerciseMediaContext = createContext<Record<string, ExerciseMedia> | null>(null);

export function ExerciseMediaProvider({
  media,
  children,
}: {
  media?: Record<string, ExerciseMedia> | null;
  children: ReactNode;
}) {
  return <ExerciseMediaContext.Provider value={media ?? null}>{children}</ExerciseMediaContext.Provider>;
}

export function useExerciseMedia(displayName: string | null | undefined): ExerciseMedia | null {
  const map = useContext(ExerciseMediaContext);
  if (!map || !displayName) return null;
  const media = map[displayName];
  return media && typeof media.video_id === "string" && media.video_id ? media : null;
}

// ---------------------------------------------------------------------------
// Demo player
// ---------------------------------------------------------------------------

type DemoMode = "facade" | "loading" | "playing" | "paused" | "error";

/** How often the loop guard checks the playhead against the segment end. */
const LOOP_POLL_MS = 250;

export function ExerciseDemo({
  media,
  exerciseName,
  leadCue,
  onLeadCuePinnedChange,
}: {
  media: ExerciseMedia;
  exerciseName: string;
  /** First coaching cue, pinned under the video while the demo leads the row. */
  leadCue?: string | null;
  /** Tells the row whether the lead cue is shown here, so the cue list below
   * does not print it twice. */
  onLeadCuePinnedChange?: (pinned: boolean) => void;
}) {
  const [mode, setMode] = useState<DemoMode>("facade");
  // Server snapshot is "not watched", so SSR and hydration agree; the client
  // then reads this device's memory.
  const watched = useSyncExternalStore(
    subscribeDemoWatched,
    () => hasWatchedDemo(media.video_id),
    () => false,
  );
  const [slow, setSlow] = useState(false);
  const [muted, setMuted] = useState(true);
  const [thumbFailed, setThumbFailed] = useState(false);
  // iPhone Safari cannot fullscreen an iframe, so the control only shows
  // where the browser supports it.
  const [canFullscreen] = useState(
    () => typeof document !== "undefined" && document.fullscreenEnabled === true,
  );
  const mountRef = useRef<HTMLDivElement | null>(null);
  const playerRef = useRef<YouTubePlayer | null>(null);
  const loopTimerRef = useRef<number | null>(null);

  const start = Math.max(0, Math.floor(media.start_s || 0));
  const end = media.end_s != null && media.end_s > start ? Math.floor(media.end_s) : null;
  const segment = demoSegmentLabel(media);
  const isCoach = media.source === "coach";
  const channel = media.channel_title?.trim() || null;
  const playerActive = mode === "loading" || mode === "playing" || mode === "paused";
  const compact = watched && mode === "facade";
  const pinLeadCue = Boolean(leadCue) && !compact && mode !== "error";

  useEffect(() => {
    onLeadCuePinnedChange?.(pinLeadCue);
  }, [onLeadCuePinnedChange, pinLeadCue]);

  useEffect(() => {
    if (!playerActive || playerRef.current || !mountRef.current) return;
    let cancelled = false;
    const host = mountRef.current;

    loadYouTubeIframeApi()
      .then((YT) => {
        if (cancelled) return;
        const target = document.createElement("div");
        host.replaceChildren(target);
        playerRef.current = new YT.Player(target, {
          host: YOUTUBE_NOCOOKIE_HOST,
          videoId: media.video_id,
          width: "100%",
          height: "100%",
          playerVars: {
            autoplay: 1,
            // Muted so autoplay after the tap is allowed on iOS; the athlete
            // can turn sound on for coach demos that talk through the rep.
            mute: 1,
            playsinline: 1,
            controls: 0,
            // Keyboard shortcuts and fullscreen stay enabled; only the control
            // bar is swapped for the row's own controls below the frame.
            fs: 1,
            rel: 0,
            iv_load_policy: 3,
            start,
            ...(end != null ? { end } : {}),
          },
          events: {
            onReady: (event) => {
              if (cancelled) return;
              event.target.playVideo();
            },
            onStateChange: (event) => {
              if (cancelled) return;
              if (event.data === YT.PlayerState.PLAYING) {
                setMode("playing");
                markDemoWatched(media.video_id);
              } else if (event.data === YT.PlayerState.PAUSED) {
                setMode("paused");
              } else if (event.data === YT.PlayerState.ENDED) {
                // Loop the segment rather than falling through to YouTube's
                // end screen of unrelated videos.
                event.target.seekTo(start, true);
                event.target.playVideo();
              }
            },
            onError: () => {
              if (!cancelled) setMode("error");
            },
          },
        });
      })
      .catch(() => {
        if (!cancelled) setMode("error");
      });

    return () => {
      cancelled = true;
    };
  }, [end, media.video_id, playerActive, start]);

  // Segment loop guard: `end` only fires ENDED on the first pass, and a seek
  // (Replay) can clear it, so the playhead is also checked while playing.
  useEffect(() => {
    if (mode !== "playing" || end == null) return;
    loopTimerRef.current = window.setInterval(() => {
      const player = playerRef.current;
      if (player && player.getCurrentTime() >= end - 0.15) {
        player.seekTo(start, true);
      }
    }, LOOP_POLL_MS);
    return () => {
      if (loopTimerRef.current != null) window.clearInterval(loopTimerRef.current);
      loopTimerRef.current = null;
    };
  }, [end, mode, start]);

  // Collapsing the row unmounts the demo: stop and release the player.
  useEffect(
    () => () => {
      try {
        playerRef.current?.destroy();
      } catch {
        // The frame may already be gone (error state removed it).
      }
      playerRef.current = null;
    },
    [],
  );

  const replay = () => {
    const player = playerRef.current;
    if (!player) return;
    player.seekTo(start, true);
    player.playVideo();
  };

  const togglePlay = () => {
    const player = playerRef.current;
    if (!player) return;
    if (mode === "playing") player.pauseVideo();
    else player.playVideo();
  };

  const toggleSlow = () => {
    const next = !slow;
    playerRef.current?.setPlaybackRate(next ? 0.5 : 1);
    setSlow(next);
  };

  const enterFullscreen = () => {
    const frame = mountRef.current?.querySelector("iframe");
    frame?.requestFullscreen?.().catch(() => {
      // Refused (no user activation, or the browser blocks it): stay inline.
    });
  };

  const toggleSound = () => {
    const player = playerRef.current;
    if (!player) return;
    if (muted) player.unMute();
    else player.mute();
    setMuted(!muted);
  };

  if (mode === "error") {
    return (
      <p className="ex-demo-unavailable" role="status">
        Video unavailable. Cues below.
      </p>
    );
  }

  if (compact) {
    return (
      <button
        type="button"
        className="ex-demo-replay-strip"
        onClick={() => setMode("loading")}
        aria-label={`Replay ${exerciseName} demo`}
      >
        <span className="ex-demo-replay-thumb" aria-hidden="true">
          {thumbFailed ? null : (
            // eslint-disable-next-line @next/next/no-img-element -- remote YouTube thumbnail, not a local asset
            <img src={demoThumbnailUrl(media.video_id, "mq")} alt="" loading="lazy" onError={() => setThumbFailed(true)} />
          )}
          <span className="ex-demo-play-glyph ex-demo-play-glyph-sm" />
        </span>
        <span className="ex-demo-replay-label">Replay demo</span>
        <span className="ex-demo-replay-meta">Watched</span>
      </button>
    );
  }

  return (
    <div className="ex-demo" data-mode={mode}>
      <div className="ex-demo-frame">
        {playerActive ? (
          <div ref={mountRef} className="ex-demo-player" />
        ) : (
          <button
            type="button"
            className="ex-demo-facade"
            onClick={() => setMode("loading")}
            aria-label={`Play ${exerciseName} demo`}
          >
            {thumbFailed ? null : (
              // eslint-disable-next-line @next/next/no-img-element -- remote YouTube thumbnail, not a local asset
              <img
                src={demoThumbnailUrl(media.video_id)}
                alt=""
                loading="lazy"
                className="ex-demo-thumb"
                onError={() => setThumbFailed(true)}
              />
            )}
            <span className="ex-demo-play-glyph" aria-hidden="true" />
          </button>
        )}
      </div>

      {/* Nothing is drawn over the frame: labels and attribution sit under
          it, and the full video is one tap away before and during playback. */}
      <div className="ex-demo-caption">
        {isCoach ? <span className="ex-demo-badge">Coach demo</span> : null}
        <span className="ex-demo-meta">
          {["Demo", segment, channel].filter(Boolean).join(" · ")}
        </span>
        <a className="ex-demo-external" href={demoFullVideoUrl(media)} target="_blank" rel="noopener noreferrer">
          Watch on YouTube
        </a>
      </div>

      {playerActive ? (
        <div className="ex-demo-controls" role="group" aria-label="Demo controls">
          <button type="button" className="ex-demo-control" onClick={togglePlay} disabled={mode === "loading"}>
            {mode === "playing" ? "Pause" : "Play"}
          </button>
          <button type="button" className="ex-demo-control" onClick={replay} disabled={mode === "loading"}>
            Replay
          </button>
          <button
            type="button"
            className="ex-demo-control"
            onClick={toggleSlow}
            aria-pressed={slow}
            disabled={mode === "loading"}
          >
            0.5×
          </button>
          <button
            type="button"
            className="ex-demo-control"
            onClick={toggleSound}
            aria-pressed={!muted}
            disabled={mode === "loading"}
          >
            {muted ? "Sound off" : "Sound on"}
          </button>
          {canFullscreen ? (
            <button type="button" className="ex-demo-control" onClick={enterFullscreen} disabled={mode === "loading"}>
              Full screen
            </button>
          ) : null}
        </div>
      ) : null}

      {pinLeadCue ? (
        <p className="ex-demo-lead-cue">
          <span className="sp-stat-label">Key cue</span>
          {leadCue}
        </p>
      ) : null}
    </div>
  );
}
