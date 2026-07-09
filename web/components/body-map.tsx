"use client";

import { useState, type KeyboardEvent } from "react";

export type BodyMapSide = "front" | "back";
export type BodyMapLayer = "muscle" | "joint";
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
  // Tap/hit radius. Muscles draw at their rx/ry instead; joints draw a small
  // precise point but keep this full radius as an invisible hit circle so
  // phone tap targets stay large.
  r: number;
  // Which anatomy layer the zone belongs to. "muscle" zones show on the
  // Muscles layer, "joint" zones on the Joints & bones layer, and "both"
  // zones (head, shoulders, shins, spine) on either. A marked zone is always
  // rendered regardless of the active layer so a selection can never vanish
  // behind the toggle.
  layer: "muscle" | "joint" | "both";
  // Forces a render style regardless of the active layer (the head is always
  // a soft region — a tiny "joint point" head would read wrong).
  kind?: "muscle" | "joint";
  // Soft-ellipse dimensions used when the zone renders muscle-style. `rot`
  // tilts the ellipse (degrees, clockwise) so arm muscles follow the limb.
  rx?: number;
  ry?: number;
  rot?: number;
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
//
// Zone labels double as the injury's free-text area, so every label must be a
// phrase the shared injury location vocabulary (fightcamp LOCATION_MAP)
// resolves — bicep, forearm, groin, ribs, hand, foot, traps, tricep, Achilles
// are all known locations.
const FRONT_ZONES: Record<string, Zone> = {
  head: { label: "Head / Neck", cx: 90, cy: 28, r: 16, layer: "both", kind: "muscle", rx: 13, ry: 15 },
  l_shoulder: { label: "Left shoulder", cx: 124, cy: 68, r: 13, layer: "both", rx: 11, ry: 9, rot: 20 },
  r_shoulder: { label: "Right shoulder", cx: 56, cy: 68, r: 13, layer: "both", rx: 11, ry: 9, rot: -20 },
  chest: { label: "Chest", cx: 90, cy: 88, r: 14, layer: "muscle", rx: 20, ry: 11 },
  l_bicep: { label: "Left bicep", cx: 133, cy: 94, r: 10, layer: "muscle", rx: 6.5, ry: 12, rot: -19 },
  r_bicep: { label: "Right bicep", cx: 47, cy: 94, r: 10, layer: "muscle", rx: 6.5, ry: 12, rot: 19 },
  ribs: { label: "Ribs", cx: 90, cy: 106, r: 11, layer: "joint" },
  l_elbow: { label: "Left elbow", cx: 141, cy: 118, r: 10, layer: "joint" },
  r_elbow: { label: "Right elbow", cx: 39, cy: 118, r: 10, layer: "joint" },
  core: { label: "Core", cx: 90, cy: 122, r: 14, layer: "muscle", rx: 13, ry: 15 },
  l_forearm: { label: "Left forearm", cx: 146, cy: 137, r: 9, layer: "muscle", rx: 6, ry: 12, rot: -15 },
  r_forearm: { label: "Right forearm", cx: 34, cy: 137, r: 9, layer: "muscle", rx: 6, ry: 12, rot: 15 },
  l_wrist: { label: "Left wrist", cx: 151, cy: 156, r: 9, layer: "joint" },
  r_wrist: { label: "Right wrist", cx: 29, cy: 156, r: 9, layer: "joint" },
  l_hip: { label: "Left hip", cx: 110, cy: 155, r: 12, layer: "joint" },
  r_hip: { label: "Right hip", cx: 70, cy: 155, r: 12, layer: "joint" },
  groin: { label: "Groin", cx: 90, cy: 168, r: 9, layer: "muscle", rx: 10, ry: 7 },
  l_hand: { label: "Left hand", cx: 159, cy: 181, r: 9, layer: "joint" },
  r_hand: { label: "Right hand", cx: 21, cy: 181, r: 9, layer: "joint" },
  l_quad: { label: "Left quad", cx: 105, cy: 190, r: 12, layer: "muscle", rx: 9, ry: 17 },
  r_quad: { label: "Right quad", cx: 75, cy: 190, r: 12, layer: "muscle", rx: 9, ry: 17 },
  l_knee: { label: "Left knee", cx: 105, cy: 220, r: 10, layer: "joint" },
  r_knee: { label: "Right knee", cx: 75, cy: 220, r: 10, layer: "joint" },
  l_shin: { label: "Left shin", cx: 105, cy: 252, r: 10, layer: "both", rx: 6, ry: 16 },
  r_shin: { label: "Right shin", cx: 75, cy: 252, r: 10, layer: "both", rx: 6, ry: 16 },
  l_ankle: { label: "Left ankle", cx: 105, cy: 282, r: 9, layer: "joint" },
  r_ankle: { label: "Right ankle", cx: 75, cy: 282, r: 9, layer: "joint" },
  l_foot: { label: "Left foot", cx: 114, cy: 300, r: 9, layer: "joint" },
  r_foot: { label: "Right foot", cx: 66, cy: 300, r: 9, layer: "joint" },
};

// Back view is NOT a mirror: the athlete's left sits on the viewer's left. So
// every "Left" zone takes the lower cx and every "Right" zone the higher cx —
// the opposite of FRONT_ZONES — while the anatomical labels stay the same.
const BACK_ZONES: Record<string, Zone> = {
  head: { label: "Head / Neck", cx: 90, cy: 28, r: 16, layer: "both", kind: "muscle", rx: 13, ry: 15 },
  traps: { label: "Traps", cx: 90, cy: 58, r: 9, layer: "muscle", rx: 13, ry: 6.5 },
  l_shoulder: { label: "Left shoulder", cx: 56, cy: 68, r: 13, layer: "both", rx: 11, ry: 9, rot: -20 },
  r_shoulder: { label: "Right shoulder", cx: 124, cy: 68, r: 13, layer: "both", rx: 11, ry: 9, rot: 20 },
  upper_back: { label: "Upper back", cx: 90, cy: 90, r: 13, layer: "both", rx: 15, ry: 12 },
  l_tricep: { label: "Left tricep", cx: 47, cy: 94, r: 10, layer: "muscle", rx: 6.5, ry: 12, rot: 19 },
  r_tricep: { label: "Right tricep", cx: 133, cy: 94, r: 10, layer: "muscle", rx: 6.5, ry: 12, rot: -19 },
  l_elbow: { label: "Left elbow", cx: 39, cy: 118, r: 10, layer: "joint" },
  r_elbow: { label: "Right elbow", cx: 141, cy: 118, r: 10, layer: "joint" },
  lower_back: { label: "Lower back", cx: 90, cy: 126, r: 14, layer: "both", rx: 12, ry: 10 },
  l_forearm: { label: "Left forearm", cx: 34, cy: 137, r: 9, layer: "muscle", rx: 6, ry: 12, rot: 15 },
  r_forearm: { label: "Right forearm", cx: 146, cy: 137, r: 9, layer: "muscle", rx: 6, ry: 12, rot: -15 },
  l_wrist: { label: "Left wrist", cx: 29, cy: 156, r: 9, layer: "joint" },
  r_wrist: { label: "Right wrist", cx: 151, cy: 156, r: 9, layer: "joint" },
  l_hip: { label: "Left hip", cx: 70, cy: 150, r: 11, layer: "joint" },
  r_hip: { label: "Right hip", cx: 110, cy: 150, r: 11, layer: "joint" },
  l_glute: { label: "Left glute", cx: 70, cy: 158, r: 12, layer: "muscle", rx: 9.5, ry: 8 },
  r_glute: { label: "Right glute", cx: 110, cy: 158, r: 12, layer: "muscle", rx: 9.5, ry: 8 },
  l_hand: { label: "Left hand", cx: 21, cy: 181, r: 9, layer: "joint" },
  r_hand: { label: "Right hand", cx: 159, cy: 181, r: 9, layer: "joint" },
  l_ham: { label: "Left hamstring", cx: 75, cy: 190, r: 12, layer: "muscle", rx: 9, ry: 16 },
  r_ham: { label: "Right hamstring", cx: 105, cy: 190, r: 12, layer: "muscle", rx: 9, ry: 16 },
  l_knee: { label: "Left knee", cx: 75, cy: 220, r: 10, layer: "joint" },
  r_knee: { label: "Right knee", cx: 105, cy: 220, r: 10, layer: "joint" },
  l_calf: { label: "Left calf", cx: 75, cy: 252, r: 10, layer: "muscle", rx: 6.5, ry: 14 },
  r_calf: { label: "Right calf", cx: 105, cy: 252, r: 10, layer: "muscle", rx: 6.5, ry: 14 },
  l_achilles: { label: "Left Achilles", cx: 75, cy: 264, r: 8, layer: "joint" },
  r_achilles: { label: "Right Achilles", cx: 105, cy: 264, r: 8, layer: "joint" },
  l_ankle: { label: "Left ankle", cx: 75, cy: 283, r: 9, layer: "joint" },
  r_ankle: { label: "Right ankle", cx: 105, cy: 283, r: 9, layer: "joint" },
};

// Radius of the visible point drawn for joint-style zones. The tap target is
// the zone's full (invisible) hit radius, not this dot.
const JOINT_POINT_RADIUS = 4.5;

// Half of the body outline (the viewer-left side, x < 90). The full figure is
// this path plus a mirrored <use> across the vertical centre line x=90, which
// guarantees the silhouette stays symmetric. The path is deliberately left
// open: the fill auto-closes it straight up the centre line (so the torso
// fills solid) while the stroke skips that closing edge, avoiding a visible
// seam down the middle of the figure.
const SILHOUETTE_HALF = [
  "M90 34 L84 35",
  "C83.6 40 83 44 79 47",
  "C68 51 57 55 52.5 62",
  "C46.5 68 43.5 76 42.5 84",
  "C41.5 95 39.5 106 37.5 117",
  "C35.5 124 33.5 131 31.5 138",
  "C29.5 146 27.5 152 25.5 159",
  "C23.5 166 21.5 172 20.5 178",
  "C19.5 184 20.5 190 23.5 191",
  "C26.5 192 28.5 188 29.5 183",
  "C31 176 32 170 34 163",
  "C36 155 38 147 40 139",
  "C42 131 44 124 46 117",
  "C48 108 50 98 52.5 90",
  "C53.5 86 55 83 57 81",
  "C58 92 59 102 60 112",
  "C61 121 61.5 128 62.5 136",
  "C63.5 144 61.5 150 60.5 157",
  "C59.5 166 60.5 174 62.5 182",
  "C64.5 193 65.5 204 66.5 214",
  "C66.5 222 65.5 229 66.5 236",
  "C67.5 246 66.5 256 68.5 266",
  "C69.5 274 69.5 281 70.5 287",
  "C70.5 293 68.5 297 64.5 300",
  "C61 303 61 307 65 308",
  "L80 308",
  "C83 307 84 302 84 297",
  "C83.5 288 82.5 278 82.5 268",
  "C81.5 257 82.5 246 83.5 237",
  "C84.5 229 84.5 222 85.5 214",
  "C86.5 203 87.5 193 88.5 184",
  "C89.5 178 90 174 90 171",
].join(" ");

const SEVERITY_LABELS: Record<BodyMapSeverity, string> = {
  low: "low severity",
  moderate: "moderate severity",
  high: "high severity",
};

const LAYER_OPTIONS: Array<{ value: BodyMapLayer; label: string }> = [
  { value: "muscle", label: "Muscles" },
  { value: "joint", label: "Joints & bones" },
];

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
  layer,
  selections,
  onZoneSelect,
  hoverKey,
  setHoverKey,
}: {
  side: BodyMapSide;
  layer: BodyMapLayer;
  selections: BodyMapSelection[];
  onZoneSelect: (zone: string, label: string) => void;
  hoverKey: string | null;
  setHoverKey: (key: string | null) => void;
}) {
  const zones = side === "front" ? FRONT_ZONES : BACK_ZONES;
  const sideLabel = side === "front" ? "Front" : "Back";
  const gradientId = `body-map-silhouette-gradient-${side}`;
  const halfId = `body-map-silhouette-half-${side}`;

  return (
    <div className={`body-map-svg-wrap body-map-svg-wrap-${side}`} data-side={side}>
      <p className="body-map-side-label" aria-hidden="true">
        {sideLabel}
      </p>
      <svg
        viewBox="0 0 180 316"
        role="group"
        aria-label={`${sideLabel} body map for injury selection`}
      >
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.16" />
            <stop offset="55%" stopColor="currentColor" stopOpacity="0.09" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0.04" />
          </linearGradient>
        </defs>
        <g className="body-map-silhouette" style={{ fill: `url(#${gradientId})` }}>
          <ellipse cx={90} cy={21} rx={13} ry={16} />
          <path id={halfId} d={SILHOUETTE_HALF} />
          {/* Mirror of the half outline across x=90 keeps the figure symmetric. */}
          <use href={`#${halfId}`} transform="scale(-1 1) translate(-180 0)" />
        </g>
        {Object.entries(zones).map(([key, zone]) => {
          const selection = findSelectionForZone(selections, key, zone.label);
          const isUsed = Boolean(selection);
          // Zones outside the active layer stay hidden unless already marked,
          // so switching layers can never hide a selection.
          if (!isUsed && zone.layer !== "both" && zone.layer !== layer) {
            return null;
          }
          // Muscles render as soft anatomical ellipses; joints as small
          // precise points. "both" zones follow the active layer's style
          // (delt vs shoulder joint) unless the zone forces a kind.
          const styleKind: BodyMapLayer =
            zone.kind ?? (zone.layer === "both" ? layer : zone.layer);
          const isHover = hoverKey === key;
          const ariaLabel = buildZoneAriaLabel(zone.label, selection);
          const zoneClass = [
            "body-map-zone",
            styleKind === "muscle" ? "body-map-zone-muscle" : "body-map-zone-joint",
            isUsed ? "body-map-zone-used" : "",
            isHover ? "body-map-zone-hover" : "",
          ]
            .filter(Boolean)
            .join(" ");

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
              {styleKind === "muscle" ? (
                <>
                  <ellipse
                    cx={zone.cx}
                    cy={zone.cy}
                    rx={zone.rx ?? zone.r}
                    ry={zone.ry ?? zone.r}
                    transform={
                      zone.rot ? `rotate(${zone.rot} ${zone.cx} ${zone.cy})` : undefined
                    }
                    className={zoneClass}
                  />
                  {isUsed ? (
                    <circle cx={zone.cx} cy={zone.cy} r={3} className="body-map-zone-dot" />
                  ) : null}
                </>
              ) : (
                <>
                  {/* Invisible hit circle keeps the tap target full-size while
                      the visible joint point stays small and precise. */}
                  <circle
                    cx={zone.cx}
                    cy={zone.cy}
                    r={Math.max(zone.r, 10)}
                    className="body-map-zone-hit"
                  />
                  <circle
                    cx={zone.cx}
                    cy={zone.cy}
                    r={JOINT_POINT_RADIUS}
                    className={zoneClass}
                  />
                </>
              )}
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
  const [layer, setLayer] = useState<BodyMapLayer>("muscle");
  const hoverLabel = hoverKey
    ? FRONT_ZONES[hoverKey]?.label ?? BACK_ZONES[hoverKey]?.label ?? ""
    : "";
  const hasAnyMarked = selections.some((entry) => entry.label.trim());

  return (
    <div className="body-map-panel" data-active-side={side}>
      <p className="body-map-title">Add injury area</p>
      <div
        className="body-map-toggle body-map-layer-toggle"
        role="tablist"
        aria-label="Body map layer"
      >
        {LAYER_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={layer === option.value}
            className={`body-map-toggle-btn ${layer === option.value ? "body-map-toggle-btn-active" : ""}`}
            onClick={() => setLayer(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      <div className="body-map-svg-stack">
        <BodySvg
          side="front"
          layer={layer}
          selections={selections}
          onZoneSelect={onZoneSelect}
          hoverKey={hoverKey}
          setHoverKey={setHoverKey}
        />
        <BodySvg
          side="back"
          layer={layer}
          selections={selections}
          onZoneSelect={onZoneSelect}
          hoverKey={hoverKey}
          setHoverKey={setHoverKey}
        />
      </div>
      <div
        className="body-map-toggle body-map-side-toggle"
        role="tablist"
        aria-label="Body map side"
      >
        <button
          type="button"
          role="tab"
          aria-selected={side === "front"}
          className={`body-map-toggle-btn ${side === "front" ? "body-map-toggle-btn-active" : ""}`}
          onClick={() => onSideChange("front")}
        >
          Front
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={side === "back"}
          className={`body-map-toggle-btn ${side === "back" ? "body-map-toggle-btn-active" : ""}`}
          onClick={() => onSideChange("back")}
        >
          Back
        </button>
      </div>
      <p className="body-map-hint" aria-live="polite">
        {hoverLabel ? (
          <span className="body-map-hint-zone">{hoverLabel}</span>
        ) : hasAnyMarked ? (
          "Tap another zone, or tap the marked zone again to raise severity."
        ) : layer === "muscle" ? (
          "Tap where it hurts — switch to Joints & bones for knees, hands or ribs."
        ) : (
          "Tap where it hurts — switch to Muscles for quads, hamstrings or calves."
        )}
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
