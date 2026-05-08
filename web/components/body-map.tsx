"use client";

import { useState, type KeyboardEvent } from "react";

export type BodyMapSide = "front" | "back";
export type BodyMapSeverity = "low" | "moderate" | "high";

export type BodyMapSelection = {
  label: string;
  severity?: BodyMapSeverity | "";
};

type Zone = {
  displayLabel: string;
  value: string;
  cx: number;
  cy: number;
  rx: number;
  ry: number;
};

const FRONT_ZONES: Record<string, Zone> = {
  head: { displayLabel: "Head", value: "Head", cx: 90, cy: 24, rx: 17, ry: 16 },
  neck: { displayLabel: "Neck", value: "Neck", cx: 90, cy: 46, rx: 10, ry: 8 },
  l_shoulder: { displayLabel: "Shoulder", value: "Left shoulder", cx: 58, cy: 66, rx: 14, ry: 10 },
  r_shoulder: { displayLabel: "Shoulder", value: "Right shoulder", cx: 122, cy: 66, rx: 14, ry: 10 },
  chest: { displayLabel: "Chest", value: "Chest", cx: 90, cy: 84, rx: 21, ry: 16 },
  l_arm: { displayLabel: "Arm", value: "Left arm", cx: 40, cy: 104, rx: 12, ry: 18 },
  r_arm: { displayLabel: "Arm", value: "Right arm", cx: 140, cy: 104, rx: 12, ry: 18 },
  l_elbow: { displayLabel: "Elbow", value: "Left elbow", cx: 36, cy: 132, rx: 10, ry: 8 },
  r_elbow: { displayLabel: "Elbow", value: "Right elbow", cx: 144, cy: 132, rx: 10, ry: 8 },
  l_wrist: { displayLabel: "Wrist", value: "Left wrist", cx: 30, cy: 156, rx: 9, ry: 7 },
  r_wrist: { displayLabel: "Wrist", value: "Right wrist", cx: 150, cy: 156, rx: 9, ry: 7 },
  l_hand: { displayLabel: "Hand", value: "Left hand", cx: 26, cy: 176, rx: 10, ry: 8 },
  r_hand: { displayLabel: "Hand", value: "Right hand", cx: 154, cy: 176, rx: 10, ry: 8 },
  l_hip: { displayLabel: "Hip", value: "Left hip", cx: 72, cy: 150, rx: 12, ry: 10 },
  r_hip: { displayLabel: "Hip", value: "Right hip", cx: 108, cy: 150, rx: 12, ry: 10 },
  groin: { displayLabel: "Groin", value: "Groin", cx: 90, cy: 162, rx: 11, ry: 9 },
  l_thigh: { displayLabel: "Thigh", value: "Left thigh", cx: 74, cy: 190, rx: 12, ry: 18 },
  r_thigh: { displayLabel: "Thigh", value: "Right thigh", cx: 106, cy: 190, rx: 12, ry: 18 },
  l_knee: { displayLabel: "Knee", value: "Left knee", cx: 74, cy: 220, rx: 11, ry: 8 },
  r_knee: { displayLabel: "Knee", value: "Right knee", cx: 106, cy: 220, rx: 11, ry: 8 },
  l_shin: { displayLabel: "Shin", value: "Left shin", cx: 74, cy: 248, rx: 10, ry: 13 },
  r_shin: { displayLabel: "Shin", value: "Right shin", cx: 106, cy: 248, rx: 10, ry: 13 },
  l_ankle: { displayLabel: "Ankle", value: "Left ankle", cx: 72, cy: 275, rx: 9, ry: 7 },
  r_ankle: { displayLabel: "Ankle", value: "Right ankle", cx: 108, cy: 275, rx: 9, ry: 7 },
  l_foot: { displayLabel: "Foot", value: "Left foot", cx: 70, cy: 292, rx: 11, ry: 7 },
  r_foot: { displayLabel: "Foot", value: "Right foot", cx: 110, cy: 292, rx: 11, ry: 7 },
};

const BACK_ZONES: Record<string, Zone> = {
  head: { displayLabel: "Head", value: "Head", cx: 90, cy: 24, rx: 17, ry: 16 },
  neck: { displayLabel: "Neck", value: "Neck", cx: 90, cy: 46, rx: 10, ry: 8 },
  l_shoulder: { displayLabel: "Shoulder", value: "Left shoulder", cx: 58, cy: 66, rx: 14, ry: 10 },
  r_shoulder: { displayLabel: "Shoulder", value: "Right shoulder", cx: 122, cy: 66, rx: 14, ry: 10 },
  upper_back: { displayLabel: "Upper Back", value: "Upper back", cx: 90, cy: 84, rx: 21, ry: 14 },
  l_arm: { displayLabel: "Arm", value: "Left arm", cx: 40, cy: 104, rx: 12, ry: 18 },
  r_arm: { displayLabel: "Arm", value: "Right arm", cx: 140, cy: 104, rx: 12, ry: 18 },
  l_elbow: { displayLabel: "Elbow", value: "Left elbow", cx: 36, cy: 132, rx: 10, ry: 8 },
  r_elbow: { displayLabel: "Elbow", value: "Right elbow", cx: 144, cy: 132, rx: 10, ry: 8 },
  l_wrist: { displayLabel: "Wrist", value: "Left wrist", cx: 30, cy: 156, rx: 9, ry: 7 },
  r_wrist: { displayLabel: "Wrist", value: "Right wrist", cx: 150, cy: 156, rx: 9, ry: 7 },
  l_hand: { displayLabel: "Hand", value: "Left hand", cx: 26, cy: 176, rx: 10, ry: 8 },
  r_hand: { displayLabel: "Hand", value: "Right hand", cx: 154, cy: 176, rx: 10, ry: 8 },
  lower_back: { displayLabel: "Lower Back", value: "Lower back", cx: 90, cy: 124, rx: 19, ry: 14 },
  l_hip: { displayLabel: "Hip", value: "Left hip", cx: 72, cy: 150, rx: 12, ry: 10 },
  r_hip: { displayLabel: "Hip", value: "Right hip", cx: 108, cy: 150, rx: 12, ry: 10 },
  l_thigh: { displayLabel: "Thigh", value: "Left thigh", cx: 74, cy: 190, rx: 12, ry: 18 },
  r_thigh: { displayLabel: "Thigh", value: "Right thigh", cx: 106, cy: 190, rx: 12, ry: 18 },
  l_knee: { displayLabel: "Knee", value: "Left knee", cx: 74, cy: 220, rx: 11, ry: 8 },
  r_knee: { displayLabel: "Knee", value: "Right knee", cx: 106, cy: 220, rx: 11, ry: 8 },
  l_shin: { displayLabel: "Shin", value: "Left shin", cx: 74, cy: 248, rx: 10, ry: 13 },
  r_shin: { displayLabel: "Shin", value: "Right shin", cx: 106, cy: 248, rx: 10, ry: 13 },
  l_ankle: { displayLabel: "Ankle", value: "Left ankle", cx: 72, cy: 275, rx: 9, ry: 7 },
  r_ankle: { displayLabel: "Ankle", value: "Right ankle", cx: 108, cy: 275, rx: 9, ry: 7 },
  l_foot: { displayLabel: "Foot", value: "Left foot", cx: 70, cy: 292, rx: 11, ry: 7 },
  r_foot: { displayLabel: "Foot", value: "Right foot", cx: 110, cy: 292, rx: 11, ry: 7 },
};

const SILHOUETTE_PATH = ["M76 41 C62 48,52 58,50 72 L46 100 Q44 112,38 122 L26 148 Q22 156,26 160", "M104 41 C118 48,128 58,130 72 L134 100 Q136 112,142 122 L154 148 Q158 156,154 160", "M76 41 Q72 50,70 62 L68 100 Q66 130,68 148 L70 168 Q72 180,74 195 L76 220 Q76 240,74 260 L72 280 Q70 292,66 298", "M104 41 Q108 50,110 62 L112 100 Q114 130,112 148 L110 168 Q108 180,106 195 L104 220 Q104 240,106 260 L108 280 Q110 292,114 298", "M70 148 Q90 156,110 148"].join(" ");
const SEVERITY_LABELS: Record<BodyMapSeverity, string> = { low: "low severity", moderate: "moderate severity", high: "high severity" };

const findSelectionForZone = (selections: BodyMapSelection[], value: string) => selections.find((entry) => entry.label.trim().toLowerCase() === value.toLowerCase());

function BodySvg({ side, selections, onZoneSelect, hoverKey, setHoverKey, activeArea }: { side: BodyMapSide; selections: BodyMapSelection[]; onZoneSelect: (label: string) => void; hoverKey: string | null; setHoverKey: (key: string | null) => void; activeArea: string; }) {
  const zones = side === "front" ? FRONT_ZONES : BACK_ZONES;
  return <div className={`body-map-svg-wrap body-map-svg-wrap-${side}`} data-side={side}><svg viewBox="0 0 180 300" role="group" aria-label={`${side} body map for injury selection`}><g className="body-map-silhouette"><ellipse cx={90} cy={24} rx={14} ry={17} /><path d={SILHOUETTE_PATH} /></g>{Object.entries(zones).map(([key, zone]) => {
    const selection = findSelectionForZone(selections, zone.value);
    const isHover = hoverKey === key;
    const isUsed = Boolean(selection);
    const isActive = activeArea === zone.value.toLowerCase();
    const badge = selections.findIndex((entry) => entry.label.trim().toLowerCase() === zone.value.toLowerCase()) + 1;
    const ariaLabel = !selection ? `${zone.value}, not marked. Press Enter to add as an injury.` : `${zone.value}, marked${selection.severity ? ` at ${SEVERITY_LABELS[selection.severity]}` : ""}. Press Enter to focus this injury card.`;
    const handleKey = (event: KeyboardEvent<SVGGElement>) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onZoneSelect(zone.value); } };
    return <g key={key} role="button" tabIndex={0} aria-label={ariaLabel} aria-pressed={isUsed} className={["body-map-zone-group", isUsed ? "body-map-zone-group-used" : "", isActive ? "body-map-zone-group-active" : "", selection?.severity ? `body-map-zone-severity-${selection.severity}` : ""].filter(Boolean).join(" ")} onMouseEnter={() => setHoverKey(key)} onMouseLeave={() => setHoverKey(null)} onFocus={() => setHoverKey(key)} onBlur={() => setHoverKey(null)} onClick={() => onZoneSelect(zone.value)} onKeyDown={handleKey}><ellipse cx={zone.cx} cy={zone.cy} rx={zone.rx} ry={zone.ry} className={`body-map-zone ${isUsed ? "body-map-zone-used" : ""} ${isHover ? "body-map-zone-hover" : ""}`} />{(isHover || isActive) ? <text x={zone.cx} y={Math.max(16, zone.cy - zone.ry - 6)} textAnchor="middle" className="body-map-zone-label">{zone.displayLabel}</text> : null}{isUsed ? <><circle cx={zone.cx} cy={zone.cy} r={5} className="body-map-zone-dot" /><text x={zone.cx} y={zone.cy + 1} textAnchor="middle" className="body-map-zone-count">{badge}</text></> : null}</g>;
  })}</svg></div>;
}

interface BodyMapProps { side: BodyMapSide; selections: BodyMapSelection[]; onZoneSelect: (label: string) => void; onSideChange: (side: BodyMapSide) => void; activeArea: string; }

export function BodyMap({ side, selections, onZoneSelect, onSideChange, activeArea }: BodyMapProps) {
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const activeZones = side === "front" ? FRONT_ZONES : BACK_ZONES;
  const hoverLabel = hoverKey ? activeZones[hoverKey]?.value ?? "" : "";
  const hasAnyMarked = selections.some((entry) => entry.label.trim());

  return <div className="body-map-panel" data-active-side={side}><p className="body-map-title">Tap an area to add or edit an injury.</p><div className="body-map-side-toggle" role="tablist" aria-label="Body map side"><button type="button" role="tab" aria-selected={side === "front"} className={`body-map-side-btn ${side === "front" ? "body-map-side-btn-active" : ""}`} onClick={() => onSideChange("front")}>Front</button><button type="button" role="tab" aria-selected={side === "back"} className={`body-map-side-btn ${side === "back" ? "body-map-side-btn-active" : ""}`} onClick={() => onSideChange("back")}>Back</button></div><div className="body-map-svg-stack"><BodySvg side={side} selections={selections} onZoneSelect={onZoneSelect} hoverKey={hoverKey} setHoverKey={setHoverKey} activeArea={activeArea} /></div><p className="body-map-hint" aria-live="polite">{hoverLabel || "Tap an area to add or edit an injury."}</p>{hasAnyMarked ? <ul className="body-map-legend" aria-label="Severity colour key"><li className="body-map-legend-item"><span className="body-map-legend-swatch body-map-legend-swatch-low" aria-hidden="true" /><span>Low</span></li><li className="body-map-legend-item"><span className="body-map-legend-swatch body-map-legend-swatch-moderate" aria-hidden="true" /><span>Moderate</span></li><li className="body-map-legend-item"><span className="body-map-legend-swatch body-map-legend-swatch-high" aria-hidden="true" /><span>High</span></li></ul> : null}</div>;
}
