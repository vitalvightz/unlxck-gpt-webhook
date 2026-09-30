"use client";

import { useId, useState } from "react";

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
  head: { label: "Head / Neck", cx: 90, cy: 21, r: 17, layer: "both", kind: "muscle", rx: 13, ry: 16 },
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
  head: { label: "Head / Neck", cx: 90, cy: 21, r: 17, layer: "both", kind: "muscle", rx: 13, ry: 16 },
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
  "C67 49 55 54 50.5 63",
  "C44 69 42 77 41.5 85",
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
  "C58 92 60 103 63 112",
  "C66 122 68 130 65 139",
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

function zonePath(key: string, zone: Zone): string {
  const { cx: x, cy: y } = zone;
  const w = zone.rx ?? 7; const h = zone.ry ?? 7;
  if (key === "head") return "M77 21a13 16 0 1 0 26 0a13 16 0 1 0-26 0";
  if (key === "chest") return "M63 76Q75 73 88 78L88 94Q75 97 66 88Z M92 78Q105 73 117 76L114 88Q105 97 92 94Z";
  if (key === "core") return "M77 105Q90 108 103 105L99 135Q90 145 81 135Z";
  if (key === "upper_back") return "M65 72Q77 68 88 78L87 102Q73 101 65 87Z M92 78Q103 68 115 72L115 87Q107 101 93 102Z";
  if (key.endsWith("shoulder")) return `M${x-w} ${y-h*.4}Q${x-w*.5} ${y-h*1.3} ${x+w*.5} ${y-h}Q${x+w*1.2} ${y-h*.2} ${x+w} ${y+h*.5}L${x-w*.1} ${y+h}Z`;
  return `M${x-w*.65} ${y-h}Q${x+w*.5} ${y-h*1.1} ${x+w} ${y-h*.4}L${x+w*.55} ${y+h*.75}Q${x} ${y+h*1.2} ${x-w*.55} ${y+h*.65}L${x-w} ${y-h*.4}Z`;
}

interface BodyMapProps {
  side: BodyMapSide;
  selections: BodyMapSelection[];
  onZoneSelect: (zone: string, label: string) => void;
  onSideChange: (side: BodyMapSide) => void;
}

export function isMuscleBodyMapZone(zone: string): boolean {
  return FRONT_ZONES[zone]?.layer === "muscle" || BACK_ZONES[zone]?.layer === "muscle";
}

export function BodyMap({ side, selections, onZoneSelect, onSideChange }: BodyMapProps) {
  const id = useId().replace(/:/g, "");
  const [layer, setLayer] = useState<BodyMapLayer>("muscle");
  const zones = side === "front" ? FRONT_ZONES : BACK_ZONES;
  const visibleZones = Object.entries(zones).filter(([key, zone]) =>
    zone.layer === layer || zone.layer === "both" || findSelectionForZone(selections, key, zone.label),
  );
  function choose(key: string, zone: Zone) {
    onZoneSelect(key, zone.label);
  }
  return (
    <div className="body-map-panel body-map-tap-first" data-active-side={side} data-active-layer={layer}>
      <div className="body-map-toolbar">
        <p className="body-map-title">Tap the affected area</p>
        <div className="body-map-toggle body-map-side-toggle" role="group" aria-label="Body view">
          {(["front", "back"] as const).map((view) => (
            <button key={view} type="button" aria-pressed={side === view}
              className={`body-map-toggle-btn ${side === view ? "body-map-toggle-btn-active" : ""}`}
              onClick={() => { onSideChange(view); }}>
              {view === "front" ? "Front" : "Back"}
            </button>
          ))}
        </div>
      </div>
      <div className="body-map-anatomy-switch" role="group" aria-label="Anatomy layer" data-layer={layer}>
        {(["muscle", "joint"] as const).map((anatomy) => (
          <button key={anatomy} type="button" aria-pressed={layer === anatomy}
            onClick={() => { setLayer(anatomy); }}>
            {anatomy === "muscle" ? "Muscles" : "Joints & bones"}
          </button>
        ))}
      </div>
      <div className="body-map-svg-stack">
        <div className="body-map-svg-wrap">
          <div className="body-map-laterality" aria-hidden="true">
            <span>{side === "front" ? "R" : "L"}</span><span>{side === "front" ? "L" : "R"}</span>
          </div>
          <svg viewBox="0 0 180 316" role="group" aria-label={`${side} body map for injury selection`}>
            <defs><path id={`body-half-${id}`} d={SILHOUETTE_HALF} /></defs>
            <g className="body-map-silhouette">
              <ellipse cx={90} cy={21} rx={13} ry={16} />
              <use href={`#body-half-${id}`} />
              <use href={`#body-half-${id}`} transform="scale(-1 1) translate(-180 0)" />
            </g>
            <g className="body-map-contours" aria-hidden="true">
              <path d={side === "front" ? "M90 53V140 M64 100Q77 105 88 100 M92 100Q103 105 116 100 M79 117H101 M81 128H99 M69 145Q90 154 111 145 M72 177Q70 195 74 208 M108 177Q110 195 106 208 M73 235Q72 251 75 266 M107 235Q108 251 105 266" : "M90 48V145 M64 76Q77 69 86 89 M116 76Q103 69 94 89 M64 154Q77 166 90 158Q103 166 116 154"} />
            </g>
            {layer === "joint" ? <g className="body-map-contours body-map-joint-guides" aria-hidden="true">
              <path d="M56 68L39 118L29 156 M124 68L141 118L151 156 M70 155L75 220L75 282 M110 155L105 220L105 282" />
            </g> : null}
            {visibleZones.map(([key, zone]) => {
              const used = Boolean(findSelectionForZone(selections, key, zone.label));
              const joint = zone.layer === "joint" || (layer === "joint" && zone.layer === "both" && !zone.kind && key !== "upper_back" && key !== "lower_back");
              const rx = zone.rx ?? 7; const ry = zone.ry ?? 7;
              return (
                <g key={key} role="button" tabIndex={0} aria-label={zone.label} aria-pressed={used}
                  className="body-map-zone-group"
                  onClick={() => choose(key, zone)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault(); choose(key, zone);
                    }
                  }}>
                  <ellipse cx={zone.cx} cy={zone.cy} rx={Math.max(rx, zone.r)} ry={Math.max(ry, zone.r)} className="body-map-zone-hit" />
                  {joint ? <circle cx={zone.cx} cy={zone.cy} r={JOINT_POINT_RADIUS}
                    className={`body-map-zone body-map-zone-joint ${used ? "body-map-zone-used" : ""}`} /> : <path
                    className={`body-map-zone ${used ? "body-map-zone-used" : ""}`}
                    transform={zone.rot ? `rotate(${zone.rot} ${zone.cx} ${zone.cy})` : undefined}
                    d={zonePath(key, zone)} />}
                  {key === "head" && !used ? <circle cx={90} cy={21} r={JOINT_POINT_RADIUS}
                    className="body-map-zone body-map-zone-joint" aria-hidden="true" /> : null}
                  {used ? <circle cx={zone.cx} cy={zone.cy} r={2.3} className="body-map-zone-dot" /> : null}
                </g>
              );
            })}
          </svg>
        </div>
      </div>
      <p className="body-map-hint">Left and right refer to your body.</p>
    </div>
  );
}
