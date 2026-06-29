"use client";

import { useState, type KeyboardEvent } from "react";

export type BodyMapSide = "front" | "back";
export type BodyMapSeverity = "low" | "moderate" | "high";

export type BodyMapSelection = {
  // Stable zone key (e.g. "l_shoulder") used to keep the zone lit even after the
  // athlete edits the free-text area. Optional so legacy/manually-typed injuries
  // still match by label.
  zone?: string;
  label: string;
  severity?: BodyMapSeverity | "";
};

type Zone = {
  label: string;
  cx: number;
  cy: number;
  r: number;
};

// Anatomical "Left"/"Right" refer to the figure's own side. Screen position must
// differ per view because the two views are not mirror images of each other:
//
//   * FRONT view faces the athlete, so it reads like a mirror — the athlete's
//     left side appears on the viewer's right (higher cx) and vice versa. So
//     "Left" zones render at higher cx, "Right" zones at lower cx.
//   * BACK view looks at the athlete from behind, so screen and anatomy line up —
//     the athlete's left is on the viewer's left (lower cx). So "Left" zones
//     render at lower cx, "Right" zones at higher cx (see BACK_ZONES below).
//
// This keeps "tap the side you feel it on" intuitive while the label stays
// anatomically correct on both views.
const FRONT_ZONES: Record<string, Zone> = {
  head: { label: "Head / Neck", cx: 90, cy: 28, r: 16 },
  l_shoulder: { label: "Left shoulder", cx: 124, cy: 68, r: 13 },
  r_shoulder: { label: "Right shoulder", cx: 56, cy: 68, r: 13 },
  chest: { label: "Chest", cx: 90, cy: 88, r: 14 },
  l_elbow: { label: "Left elbow", cx: 142, cy: 118, r: 10 },
  r_elbow: { label: "Right elbow", cx: 38, cy: 118, r: 10 },
  core: { label: "Core", cx: 90, cy: 120, r: 14 },
  l_wrist: { label: "Left wrist", cx: 156, cy: 155, r: 9 },
  r_wrist: { label: "Right wrist", cx: 24, cy: 155, r: 9 },
  l_hip: { label: "Left hip", cx: 110, cy: 155, r: 12 },
  r_hip: { label: "Right hip", cx: 70, cy: 155, r: 12 },
  l_quad: { label: "Left quad", cx: 108, cy: 190, r: 12 },
  r_quad: { label: "Right quad", cx: 72, cy: 190, r: 12 },
  l_knee: { label: "Left knee", cx: 106, cy: 220, r: 10 },
  r_knee: { label: "Right knee", cx: 74, cy: 220, r: 10 },
  l_shin: { label: "Left shin", cx: 106, cy: 252, r: 10 },
  r_shin: { label: "Right shin", cx: 74, cy: 252, r: 10 },
  l_ankle: { label: "Left ankle", cx: 108, cy: 282, r: 9 },
  r_ankle: { label: "Right ankle", cx: 72, cy: 282, r: 9 },
};

// Back view is NOT a mirror: the athlete's left sits on the viewer's left. So
// every "Left" zone takes the lower cx and every "Right" zone the higher cx —
// the opposite of FRONT_ZONES — while the anatomical labels stay the same.
const BACK_ZONES: Record<string, Zone> = {
  head: { label: "Head / Neck", cx: 90, cy: 28, r: 16 },
  l_shoulder: { label: "Left shoulder", cx: 56, cy: 68, r: 13 },
  r_shoulder: { label: "Right shoulder", cx: 124, cy: 68, r: 13 },
  upper_back: { label: "Upper back", cx: 90, cy: 88, r: 14 },
  l_elbow: { label: "Left elbow", cx: 38, cy: 118, r: 10 },
  r_elbow: { label: "Right elbow", cx: 142, cy: 118, r: 10 },
  lower_back: { label: "Lower back", cx: 90, cy: 125, r: 14 },
  l_wrist: { label: "Left wrist", cx: 24, cy: 155, r: 9 },
  r_wrist: { label: "Right wrist", cx: 156, cy: 155, r: 9 },
  l_glute: { label: "Left glute", cx: 70, cy: 155, r: 12 },
  r_glute: { label: "Right glute", cx: 110, cy: 155, r: 12 },
  l_ham: { label: "Left hamstring", cx: 72, cy: 190, r: 12 },
  r_ham: { label: "Right hamstring", cx: 108, cy: 190, r: 12 },
  l_knee: { label: "Left knee", cx: 74, cy: 220, r: 10 },
  r_knee: { label: "Right knee", cx: 106, cy: 220, r: 10 },
  l_calf: { label: "Left calf", cx: 74, cy: 252, r: 10 },
  r_calf: { label: "Right calf", cx: 106, cy: 252, r: 10 },
  l_ankle: { label: "Left ankle", cx: 72, cy: 282, r: 9 },
  r_ankle: { label: "Right ankle", cx: 108, cy: 282, r: 9 },
};

const SILHOUETTE_PATH = [
  "M76 41 C62 48,52 58,50 72 L46 100 Q44 112,38 122 L26 148 Q22 156,26 160",
  "M104 41 C118 48,128 58,130 72 L134 100 Q136 112,142 122 L154 148 Q158 156,154 160",
  "M76 41 Q72 50,70 62 L68 100 Q66 130,68 148 L70 168 Q72 180,74 195 L76 220 Q76 240,74 260 L72 280 Q70 292,66 298",
  "M104 41 Q108 50,110 62 L112 100 Q114 130,112 148 L110 168 Q108 180,106 195 L104 220 Q104 240,106 260 L108 280 Q110 292,114 298",
  "M70 148 Q90 156,110 148",
].join(" ");

const SEVERITY_LABELS: Record<BodyMapSeverity, string> = {
  low: "low severity",
  moderate: "moderate severity",
  high: "high severity",
};

function findSelectionForZone(
  selections: BodyMapSelection[],
  zoneKey: string,
  zoneLabel: string,
): BodyMapSelection | undefined {
  // Prefer the stable zone key so the zone stays lit even after the athlete
  // rewrites the free-text area. Fall back to a label match for legacy or
  // manually-typed injuries that have no zone key yet.
  const byZone = selections.find((entry) => entry.zone && entry.zone === zoneKey);
  if (byZone) {
    return byZone;
  }
  const target = zoneLabel.toLowerCase();
  return selections.find((entry) => !entry.zone && entry.label.trim().toLowerCase() === target);
}

function severityClass(severity: BodyMapSeverity | "" | undefined): string {
  if (!severity) {
    return "";
  }
  return `body-map-zone-severity-${severity}`;
}

function buildZoneAriaLabel(
  zoneLabel: string,
  selection: BodyMapSelection | undefined,
): string {
  if (!selection) {
    return `${zoneLabel}, not marked. Press Enter to add as an injury.`;
  }
  const severity = selection.severity ? SEVERITY_LABELS[selection.severity] : null;
  if (severity) {
    return `${zoneLabel}, marked at ${severity}. Press Enter to change severity.`;
  }
  return `${zoneLabel}, marked. Press Enter to set severity.`;
}

function BodySvg({
  side,
  selections,
  onZoneSelect,
  hoverKey,
  setHoverKey,
}: {
  side: BodyMapSide;
  selections: BodyMapSelection[];
  onZoneSelect: (zone: string, label: string) => void;
  hoverKey: string | null;
  setHoverKey: (key: string | null) => void;
}) {
  const zones = side === "front" ? FRONT_ZONES : BACK_ZONES;
  const sideLabel = side === "front" ? "Front" : "Back";
  const gradientId = `body-map-silhouette-gradient-${side}`;
  const filterId = `body-map-soft-glow-${side}`;

  return (
    <div className={`body-map-svg-wrap body-map-svg-wrap-${side}`} data-side={side}>
      <p className="body-map-side-label" aria-hidden="true">
        {sideLabel}
      </p>
      <svg
        viewBox="0 0 180 300"
        role="group"
        aria-label={`${sideLabel} body map for injury selection`}
      >
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.2" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0.05" />
          </linearGradient>
          <filter id={filterId} x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="0" stdDeviation="1.6" floodColor="currentColor" floodOpacity="0.2" />
          </filter>
        </defs>
        <g className="body-map-silhouette" style={{ fill: `url(#${gradientId})`, filter: `url(#${filterId})` }}>
          <ellipse cx={90} cy={24} rx={14} ry={17} />
          <path d={SILHOUETTE_PATH} />
        </g>
        {Object.entries(zones).map(([key, zone]) => {
          const selection = findSelectionForZone(selections, key, zone.label);
          const isUsed = Boolean(selection);
          const isHover = hoverKey === key;
          const ariaLabel = buildZoneAriaLabel(zone.label, selection);

          const handleKey = (event: KeyboardEvent<SVGGElement>) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onZoneSelect(key, zone.label);
            }
          };

          return (
            <g
              key={key}
              role="button"
              tabIndex={0}
              aria-label={ariaLabel}
              aria-pressed={isUsed}
              className={[
                "body-map-zone-group",
                isUsed ? "body-map-zone-group-used" : "",
                severityClass(selection?.severity),
              ]
                .filter(Boolean)
                .join(" ")}
              onMouseEnter={() => setHoverKey(key)}
              onMouseLeave={() => setHoverKey(null)}
              onFocus={() => setHoverKey(key)}
              onBlur={() => setHoverKey(null)}
              onClick={() => onZoneSelect(key, zone.label)}
              onKeyDown={handleKey}
            >
              <circle
                cx={zone.cx}
                cy={zone.cy}
                r={zone.r}
                className={`body-map-zone ${isUsed ? "body-map-zone-used" : ""} ${isHover ? "body-map-zone-hover" : ""}`}
              />
              {isUsed ? (
                <circle
                  cx={zone.cx}
                  cy={zone.cy}
                  r={3}
                  className="body-map-zone-dot"
                />
              ) : null}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

interface BodyMapProps {
  side: BodyMapSide;
  selections: BodyMapSelection[];
  onZoneSelect: (zone: string, label: string) => void;
  onSideChange: (side: BodyMapSide) => void;
}

export function BodyMap({
  side,
  selections,
  onZoneSelect,
  onSideChange,
}: BodyMapProps) {
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const activeZones = side === "front" ? FRONT_ZONES : BACK_ZONES;
  const hoverLabel = hoverKey ? activeZones[hoverKey]?.label ?? "" : "";
  const hasAnyMarked = selections.some((entry) => entry.label.trim());

  return (
    <div className="body-map-panel" data-active-side={side}>
      <p className="body-map-title">Tap a zone to add</p>
      <div className="body-map-svg-stack">
        <BodySvg
          side="front"
          selections={selections}
          onZoneSelect={onZoneSelect}
          hoverKey={hoverKey}
          setHoverKey={setHoverKey}
        />
        <BodySvg
          side="back"
          selections={selections}
          onZoneSelect={onZoneSelect}
          hoverKey={hoverKey}
          setHoverKey={setHoverKey}
        />
      </div>
      <div className="body-map-side-toggle" role="tablist" aria-label="Body map side">
        <button
          type="button"
          role="tab"
          aria-selected={side === "front"}
          className={`body-map-side-btn ${side === "front" ? "body-map-side-btn-active" : ""}`}
          onClick={() => onSideChange("front")}
        >
          Front
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={side === "back"}
          className={`body-map-side-btn ${side === "back" ? "body-map-side-btn-active" : ""}`}
          onClick={() => onSideChange("back")}
        >
          Back
        </button>
      </div>
      <p className="body-map-hint" aria-live="polite">
        {hoverLabel ||
          (hasAnyMarked
            ? "Tap a zone to add it. Tap a marked zone to set its severity."
            : "Tap a zone, or type the area manually in a card.")}
      </p>
      {hasAnyMarked ? (
        <ul className="body-map-legend" aria-label="Severity colour key">
          <li className="body-map-legend-item">
            <span className="body-map-legend-swatch body-map-legend-swatch-low" aria-hidden="true" />
            <span>Low</span>
          </li>
          <li className="body-map-legend-item">
            <span className="body-map-legend-swatch body-map-legend-swatch-moderate" aria-hidden="true" />
            <span>Moderate</span>
          </li>
          <li className="body-map-legend-item">
            <span className="body-map-legend-swatch body-map-legend-swatch-high" aria-hidden="true" />
            <span>High</span>
          </li>
        </ul>
      ) : null}
    </div>
  );
}
