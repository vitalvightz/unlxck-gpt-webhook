"use client";

import {
  useId,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

/* ------------------------------------------------------------------ *
 * EffortSlider — Session RPE
 * A 1-9 effort scale rendered as a draggable track. No numerals are
 * ever shown; the athlete reads effort from descriptive labels only.
 * ------------------------------------------------------------------ */

const EFFORT_STEPS = 9;

// Descriptor per step (1-9). Index 0 is unused so the value maps 1:1.
const EFFORT_DESCRIPTORS = [
  "",
  "Very Light",
  "Light",
  "Easy",
  "Moderate",
  "Somewhat Hard",
  "Hard",
  "Very Hard",
  "Near Max",
  "Max Effort",
] as const;

export function EffortSlider({
  value,
  onChange,
  id,
  ariaLabel = "Effort",
}: {
  value: number | null;
  onChange: (value: number) => void;
  id?: string;
  ariaLabel?: string;
}) {
  const reactId = useId();
  const sliderId = id ?? reactId;
  const isSet = value !== null;
  // When unset, park the thumb in the middle but render it muted so it
  // never reads as a committed answer.
  const current = value ?? Math.ceil(EFFORT_STEPS / 2);
  const fillPct = ((current - 1) / (EFFORT_STEPS - 1)) * 100;
  const descriptor = isSet ? EFFORT_DESCRIPTORS[current] : "Drag to rate effort";

  return (
    <div className="effort-slider" data-empty={isSet ? undefined : "true"}>
      <div className="effort-slider-readout" aria-hidden="true">
        <span className="effort-slider-descriptor">{descriptor}</span>
      </div>
      <div
        className="effort-slider-track-wrap"
        style={{ ["--effort-fill" as string]: `${fillPct}%` }}
      >
        <input
          id={sliderId}
          className="effort-slider-input"
          type="range"
          min={1}
          max={EFFORT_STEPS}
          step={1}
          value={current}
          aria-label={ariaLabel}
          aria-valuetext={isSet ? descriptor : "Not set"}
          onChange={(event) => onChange(Number.parseInt(event.target.value, 10))}
          onClick={(event) => {
            // First tap may land on the parked thumb and fire no change
            // event, leaving the value unset. Commit the current position so
            // a single tap always registers.
            if (!isSet) {
              onChange(Number.parseInt(event.currentTarget.value, 10));
            }
          }}
        />
      </div>
      <div className="effort-slider-anchors" aria-hidden="true">
        <span>Very Light</span>
        <span>Max Effort</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * FaceScale — Pain after
 * A row of five hand-built outline faces (calm -> strained). Tap a
 * face or arrow across them. Each face maps to an integer inside the
 * backend's 0-10 pain range.
 * ------------------------------------------------------------------ */

const PAIN_LEVELS = [
  { value: 0, label: "None" },
  { value: 3, label: "Mild" },
  { value: 5, label: "Moderate" },
  { value: 7, label: "Strong" },
  { value: 10, label: "Severe" },
] as const;

export function FaceScale({
  value,
  onChange,
}: {
  value: number | null;
  onChange: (value: number) => void;
}) {
  const controlId = useId();
  const selectedIndex = PAIN_LEVELS.findIndex((level) => level.value === value);

  function move(delta: number) {
    const base = selectedIndex === -1 ? (delta > 0 ? -1 : PAIN_LEVELS.length) : selectedIndex;
    const next = Math.min(PAIN_LEVELS.length - 1, Math.max(0, base + delta));
    onChange(PAIN_LEVELS[next].value);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowRight" || event.key === "ArrowUp") {
      event.preventDefault();
      move(1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
      event.preventDefault();
      move(-1);
    } else if (event.key === "Home") {
      event.preventDefault();
      onChange(PAIN_LEVELS[0].value);
    } else if (event.key === "End") {
      event.preventDefault();
      onChange(PAIN_LEVELS[PAIN_LEVELS.length - 1].value);
    }
  }

  const activeLabel = selectedIndex === -1 ? "Not set" : PAIN_LEVELS[selectedIndex].label;

  return (
    <div className="face-scale">
      <div
        className="face-scale-row"
        role="radiogroup"
        aria-label="Pain after session"
        tabIndex={0}
        aria-activedescendant={selectedIndex !== -1 ? `${controlId}-pain-${selectedIndex}` : undefined}
        onKeyDown={handleKeyDown}
      >
        {PAIN_LEVELS.map((level, index) => {
          const selected = index === selectedIndex;
          return (
            <button
              key={level.value}
              id={`${controlId}-pain-${index}`}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={level.label}
              tabIndex={-1}
              className="face-scale-face"
              data-selected={selected ? "true" : undefined}
              onClick={() => onChange(level.value)}
            >
              <FaceIcon level={index} />
              <span className="face-scale-caption">{level.label}</span>
            </button>
          );
        })}
      </div>
      <span className="sr-only" aria-live="polite">
        {activeLabel}
      </span>
    </div>
  );
}

// Five restrained outline faces. Drawn with strokes so they inherit the
// active/muted colour. Deliberately understated — no emoji glyphs, no
// star eyes — just a shifting brow + mouth to read calm -> strained.
function FaceIcon({ level }: { level: number }) {
  // Mouth path morphs from a soft smile (0) to a tight grimace (4).
  const mouths = [
    "M9 15.5 Q12 18 15 15.5", // gentle smile
    "M9 15.8 Q12 16.8 15 15.8", // soft
    "M9.2 16 H14.8", // flat line
    "M9 16.8 Q12 15 15 16.8", // frown
    "M9 17 Q12 14.4 15 17", // deep grimace
  ];
  // Brows angle inward as pain rises (drawn only from level 2 up).
  const showBrows = level >= 2;
  const browLeft = ["", "", "M7.6 9.4 L10.2 9.9", "M7.4 9.2 L10.3 10.2", "M7.2 9 L10.4 10.6"][level];
  const browRight = ["", "", "M16.4 9.4 L13.8 9.9", "M16.6 9.2 L13.7 10.2", "M16.8 9 L13.6 10.6"][level];

  return (
    <svg
      className="face-scale-svg"
      viewBox="0 0 24 24"
      width="38"
      height="38"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9.4" strokeWidth="1.4" />
      {showBrows ? (
        <>
          <path d={browLeft} />
          <path d={browRight} />
        </>
      ) : null}
      <circle cx="8.8" cy="11.4" r="0.95" fill="currentColor" stroke="none" />
      <circle cx="15.2" cy="11.4" r="0.95" fill="currentColor" stroke="none" />
      <path d={mouths[level]} />
    </svg>
  );
}

/* ------------------------------------------------------------------ *
 * LevelSlider — Fatigue level
 * A three-position segmented slider with a sliding brand indicator.
 * ------------------------------------------------------------------ */

const LEVEL_OPTIONS = [
  { value: "low", label: "Low" },
  { value: "moderate", label: "Moderate" },
  { value: "high", label: "High" },
] as const;

export type LevelValue = (typeof LEVEL_OPTIONS)[number]["value"];

export function LevelSlider({
  value,
  onChange,
  ariaLabel = "Fatigue level",
}: {
  value: LevelValue | null;
  onChange: (value: LevelValue) => void;
  ariaLabel?: string;
}) {
  const controlId = useId();
  const selectedIndex = LEVEL_OPTIONS.findIndex((option) => option.value === value);

  function move(delta: number) {
    const base = selectedIndex === -1 ? (delta > 0 ? -1 : LEVEL_OPTIONS.length) : selectedIndex;
    const next = Math.min(LEVEL_OPTIONS.length - 1, Math.max(0, base + delta));
    onChange(LEVEL_OPTIONS[next].value);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowRight" || event.key === "ArrowUp") {
      event.preventDefault();
      move(1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
      event.preventDefault();
      move(-1);
    }
  }

  // Let a tap anywhere on the track jump to the nearest segment.
  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    const index = Math.min(LEVEL_OPTIONS.length - 1, Math.max(0, Math.round(ratio * (LEVEL_OPTIONS.length - 1))));
    onChange(LEVEL_OPTIONS[index].value);
  }

  return (
    <div
      className="level-slider"
      role="radiogroup"
      aria-label={ariaLabel}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onPointerDown={handlePointerDown}
    >
      {selectedIndex !== -1 ? (
        <span
          className="level-slider-indicator"
          aria-hidden="true"
          style={{
            ["--level-count" as string]: LEVEL_OPTIONS.length,
            ["--level-index" as string]: selectedIndex,
          }}
        />
      ) : null}
      {LEVEL_OPTIONS.map((option, index) => {
        const selected = index === selectedIndex;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={-1}
            className="level-slider-segment"
            data-selected={selected ? "true" : undefined}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
