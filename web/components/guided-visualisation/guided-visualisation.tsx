"use client";

import "./guided-visualisation.css";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { lockOverlayScroll } from "@/lib/overlay-scroll-lock";

import { formatClock } from "@/lib/session-timer/plan";
import { timerAudio } from "@/lib/session-timer/audio";
import {
  buildGuideScript,
  elapsedBefore,
  isCalmVisualisation,
  type FightVisualisation,
  type GuidePhase,
} from "@/lib/fight-visualisation/script";
import { CROWD_SOURCES, CrowdBed, crowdLevel, type FightLevel } from "@/lib/fight-visualisation/crowd";
import { primeSpeech, speakLine, speechAvailable, stopSpeech } from "@/lib/fight-visualisation/narrator";

type Status = "ready" | "playing" | "paused" | "done";

const PHASE_LABEL: Record<GuidePhase, string> = {
  settle: "Settle",
  frame: "Set the picture",
  rehearse: "Rehearse",
  anchor: "Lock the cue",
  close: "Come back",
};

const VOICE_KEY = "unlxck.guided-visualisation.voice";
const CROWD_KEY = "unlxck.guided-visualisation.crowd";

function loadPreference(key: string): boolean {
  try {
    return window.localStorage.getItem(key) !== "off";
  } catch {
    return true;
  }
}

function savePreference(key: string, on: boolean): void {
  try {
    window.localStorage.setItem(key, on ? "on" : "off");
  } catch {
    // A convenience only.
  }
}

type WakeLockSentinelLike = { release: () => Promise<void> };
type WakeLockNavigator = Navigator & {
  wakeLock?: { request: (type: "screen") => Promise<WakeLockSentinelLike> };
};

/** Keep the screen on while the voice is guiding: a locked phone stops speech. */
function useWakeLock(active: boolean): void {
  useEffect(() => {
    if (!active || typeof navigator === "undefined") return;
    const wakeLock = (navigator as WakeLockNavigator).wakeLock;
    if (!wakeLock) return;
    let sentinel: WakeLockSentinelLike | null = null;
    let cancelled = false;
    const acquire = () => {
      wakeLock
        .request("screen")
        .then((lock) => {
          if (cancelled) void lock.release().catch(() => undefined);
          else sentinel = lock;
        })
        .catch(() => undefined);
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") acquire();
    };
    acquire();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
      void sentinel?.release().catch(() => undefined);
    };
  }, [active]);
}

export function GuidedVisualisation({
  visualisation,
  firstName,
  level = "amateur",
  finishLabel,
  upNext,
  skipLabel,
  onClose,
  onFinish,
  onComplete,
  onSkip,
}: {
  visualisation: FightVisualisation;
  /** Spoken first, then once more on the cue. */
  firstName?: string | null;
  /** Picks the crowd and the venue line: a small hall or an arena. */
  level?: FightLevel;
  /** Shown on the done screen when `onFinish` is set, e.g. "Continue to training". */
  finishLabel?: string;
  /** What `onFinish` leads to, shown on the done screen ("Battle Rope Slams"). */
  upNext?: string | null;
  /** Offered while the run is set up or playing when `onSkip` is set. */
  skipLabel?: string;
  onClose: () => void;
  onFinish?: () => void;
  /** Fired once when the run reaches its end, without waiting for a tap. */
  onComplete?: () => void;
  /** Moves on without finishing (the visualisation is optional). */
  onSkip?: () => void;
}) {
  // Keyed on content, not identity: the parent rebuilds the object on every
  // render, and a new script would restart the line being spoken.
  const scriptKey = JSON.stringify(visualisation);
  const script = useMemo(
    () => buildGuideScript(JSON.parse(scriptKey) as FightVisualisation, { firstName, level }),
    [scriptKey, firstName, level],
  );
  const calm = isCalmVisualisation(visualisation);
  const [status, setStatus] = useState<Status>("ready");
  const [index, setIndex] = useState(0);
  const [holdLeft, setHoldLeft] = useState<number | null>(null);
  // The player only mounts after a tap, never on the server, so client-only
  // facts can seed state directly.
  const [canSpeak] = useState(speechAvailable);
  const [voiceOn, setVoiceOn] = useState(() => speechAvailable() && loadPreference(VOICE_KEY));
  const [crowdOn, setCrowdOn] = useState(() => loadPreference(CROWD_KEY));
  // Only offered once the loop has actually loaded: no file, no toggle.
  const [crowdReady, setCrowdReady] = useState(false);
  const crowdRef = useRef<CrowdBed | null>(null);
  // Seconds left in the current hold when it was paused; resumes from there.
  const resumeHoldRef = useRef<number | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const releaseScroll = lockOverlayScroll();
    rootRef.current?.focus({ preventScroll: true });
    return () => {
      stopSpeech();
      releaseScroll();
    };
  }, []);

  useEffect(() => {
    const bed = new CrowdBed(CROWD_SOURCES[level]);
    crowdRef.current = bed;
    let live = true;
    void bed.load().then((loaded) => {
      if (live) setCrowdReady(loaded);
    });
    return () => {
      live = false;
      bed.close();
      crowdRef.current = null;
    };
  }, [level]);

  useWakeLock(status === "playing");

  // Reaching the end is what counts as doing it; the done screen's buttons
  // only decide where to go next.
  const onCompleteRef = useRef(onComplete);
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);
  const completedRef = useRef(false);
  useEffect(() => {
    if (status === "done" && !completedRef.current) {
      completedRef.current = true;
      onCompleteRef.current?.();
    }
  }, [status]);

  useEffect(() => {
    if (status !== "playing") return;
    const segment = script.segments[index];
    if (!segment) return;
    const next = () => {
      resumeHoldRef.current = null;
      setHoldLeft(null);
      if (index + 1 >= script.segments.length) {
        setStatus("done");
        timerAudio().play("soft_chime");
      } else {
        setIndex(index + 1);
      }
    };
    if (segment.kind === "say") {
      if (voiceOn) {
        return speakLine(segment.text, { estimateSec: segment.estimateSec }, next);
      }
      const timeout = window.setTimeout(next, (segment.estimateSec + 0.8) * 1000);
      return () => window.clearTimeout(timeout);
    }
    const length = resumeHoldRef.current ?? segment.seconds;
    const endsAt = Date.now() + length * 1000;
    setHoldLeft(length);
    const interval = window.setInterval(() => {
      const left = Math.max(0, (endsAt - Date.now()) / 1000);
      resumeHoldRef.current = left;
      setHoldLeft(left);
      if (left <= 0) {
        window.clearInterval(interval);
        next();
      }
    }, 250);
    return () => window.clearInterval(interval);
  }, [status, index, voiceOn, script]);

  const currentSegment = script.segments[Math.min(index, script.segments.length - 1)];
  const speaking = status === "playing" && voiceOn && currentSegment.kind === "say";
  const crowdTarget =
    crowdOn && crowdReady && status === "playing"
      ? crowdLevel({ phase: currentSegment.phase, speaking, calm })
      : 0;
  useEffect(() => {
    // Slow glides between phases; a quicker duck when the voice comes in.
    crowdRef.current?.fadeTo(crowdTarget, status === "done" ? 3 : speaking ? 0.6 : 1.8);
  }, [crowdTarget, speaking, status]);

  function begin() {
    // Every unlock must happen inside the tap itself.
    timerAudio().unlock();
    crowdRef.current?.unlock();
    crowdRef.current?.start();
    if (voiceOn) primeSpeech();
    setIndex(0);
    resumeHoldRef.current = null;
    setStatus("playing");
  }

  function togglePause() {
    if (status === "playing") {
      stopSpeech();
      setStatus("paused");
    } else if (status === "paused") {
      timerAudio().unlock();
      crowdRef.current?.unlock();
      if (voiceOn) primeSpeech();
      setStatus("playing");
    }
  }

  function toggleCrowd() {
    const next = !crowdOn;
    if (next) {
      crowdRef.current?.unlock();
      crowdRef.current?.start();
    }
    setCrowdOn(next);
    savePreference(CROWD_KEY, next);
  }

  function toggleVoice() {
    const next = !voiceOn;
    if (next) primeSpeech();
    else stopSpeech();
    setVoiceOn(next);
    savePreference(VOICE_KEY, next);
  }

  function close() {
    stopSpeech();
    onClose();
  }

  function skip() {
    stopSpeech();
    onSkip?.();
  }

  const segment = currentSegment;
  const phase: GuidePhase = status === "ready" ? "settle" : status === "done" ? "close" : segment.phase;
  // The caption is the line being spoken, or during a hold the line just spoken.
  let caption = "";
  for (let i = Math.min(index, script.segments.length - 1); i >= 0; i -= 1) {
    const item = script.segments[i];
    if (item.kind === "say") {
      caption = item.text;
      break;
    }
  }
  const holdElapsed =
    segment.kind === "hold" && holdLeft !== null ? Math.max(0, segment.seconds - holdLeft) : 0;
  const elapsed = status === "done" ? script.totalSec : elapsedBefore(script, index) + holdElapsed;
  const progress = Math.min(1, elapsed / Math.max(1, script.totalSec));
  const remaining = Math.max(0, Math.round(script.totalSec - elapsed));
  const minutes = Math.max(1, Math.round(script.totalSec / 60));

  const player = (
    <div
      ref={rootRef}
      className="gv-root"
      role="dialog"
      aria-modal="true"
      aria-label={`Guided ${visualisation.name}`}
      data-status={status}
      data-phase={phase}
      tabIndex={-1}
      onKeyDown={(event) => {
        if (event.key === "Escape") close();
        if (event.key === " " && (status === "playing" || status === "paused")) {
          event.preventDefault();
          togglePause();
        }
      }}
    >
      <div className="gv-glow" aria-hidden="true" />
      <header className="gv-head">
        <p className="gv-kicker">Fight Visualisation</p>
        <button type="button" className="gv-icon-button" onClick={close} aria-label="Close guided visualisation">
          ×
        </button>
      </header>

      {status === "ready" ? (
        <main className="gv-ready">
          <h2 className="gv-title">{visualisation.name}</h2>
          {visualisation.why ? <p className="gv-why">{visualisation.why}</p> : null}
          <ul className="gv-facts">
            <li>About {minutes} min</li>
            <li>Eyes closed</li>
            <li>{voiceOn ? "Voice guided" : "On-screen prompts"}</li>
            {crowdReady && crowdOn ? <li>{level === "professional" ? "Arena crowd" : "Fight-hall crowd"}</li> : null}
          </ul>
          <p className="gv-hint">
            Sit or lie down somewhere quiet. Headphones help. The voice gives each step, then goes
            quiet so you can run the picture yourself.
          </p>
          <div className="gv-toggles">
            {canSpeak ? (
              <label className="gv-toggle">
                <input type="checkbox" checked={voiceOn} onChange={toggleVoice} />
                <span>Voice</span>
              </label>
            ) : null}
            {crowdReady ? (
              <label className="gv-toggle">
                <input type="checkbox" checked={crowdOn} onChange={toggleCrowd} />
                <span>Crowd</span>
              </label>
            ) : null}
          </div>
          {canSpeak ? null : (
            <p className="gv-hint">Voice is not available on this device; prompts will show on screen.</p>
          )}
          <button type="button" className="gv-primary" onClick={begin}>
            Begin
          </button>
          {onSkip ? (
            <button type="button" className="gv-link" onClick={skip}>
              {skipLabel ?? "Skip"}
            </button>
          ) : null}
        </main>
      ) : status === "done" ? (
        <main className="gv-done">
          <div className="gv-orb" aria-hidden="true" />
          <h2 className="gv-title">Done.</h2>
          {visualisation.cue ? (
            <p className="gv-cue">
              <span className="gv-cue-label">Your cue</span>
              {visualisation.cue}
            </p>
          ) : null}
          {onFinish && upNext ? (
            <p className="gv-up-next">
              <span className="gv-cue-label">Up next</span>
              {upNext}
            </p>
          ) : null}
          <div className="gv-done-actions">
            {onFinish ? (
              <button type="button" className="gv-primary" onClick={onFinish}>
                {finishLabel ?? "Done"}
              </button>
            ) : null}
            <button type="button" className={onFinish ? "gv-secondary" : "gv-primary"} onClick={close}>
              Close
            </button>
          </div>
        </main>
      ) : (
        <main className="gv-stage">
          <p className="gv-phase">{status === "paused" ? "Paused" : PHASE_LABEL[phase]}</p>
          <div className="gv-orb" aria-hidden="true" />
          <p className="gv-caption" aria-live="polite">
            {caption}
          </p>
        </main>
      )}

      {status === "playing" || status === "paused" ? (
        <footer className="gv-controls">
          <div
            className="gv-progress"
            role="progressbar"
            aria-label="Visualisation progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(progress * 100)}
          >
            <span style={{ transform: `scaleX(${progress})` }} />
          </div>
          <p className="gv-remaining">{formatClock(remaining)} left</p>
          <div className="gv-buttons">
            {canSpeak ? (
              <button type="button" className="gv-secondary" onClick={toggleVoice} aria-pressed={voiceOn}>
                {voiceOn ? "Mute voice" : "Voice on"}
              </button>
            ) : null}
            {crowdReady ? (
              <button type="button" className="gv-secondary" onClick={toggleCrowd} aria-pressed={crowdOn}>
                {crowdOn ? "Mute crowd" : "Crowd on"}
              </button>
            ) : null}
            <button type="button" className="gv-primary" onClick={togglePause}>
              {status === "paused" ? "Resume" : "Pause"}
            </button>
            <button type="button" className="gv-secondary" onClick={close}>
              End
            </button>
          </div>
          {onSkip ? (
            <button type="button" className="gv-link" onClick={skip}>
              {skipLabel ?? "Skip"}
            </button>
          ) : null}
        </footer>
      ) : null}
    </div>
  );
  // On the page body, like the session timer: it opens over the session's
  // review sheet as well as over Today.
  return typeof document === "undefined" ? player : createPortal(player, document.body);
}
