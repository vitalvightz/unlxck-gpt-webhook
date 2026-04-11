"use client";

import { useState } from "react";

export type BodyMapSide = "front" | "back";

type Zone = {
  label: string;
  cx: number;
  cy: number;
  r: number;
};

const FRONT_ZONES: Record<string, Zone> = {
  head: { label: "Head / Neck", cx: 90, cy: 28, r: 16 },
  l_shoulder: { label: "Left shoulder", cx: 56, cy: 68, r: 13 },
  r_shoulder: { label: "Right shoulder", cx: 124, cy: 68, r: 13 },
  chest: { label: "Chest", cx: 90, cy: 88, r: 14 },
  l_elbow: { label: "Left elbow", cx: 38, cy: 118, r: 10 },
  r_elbow: { label: "Right elbow", cx: 142, cy: 118, r: 10 },
  core: { label: "Core", cx: 90, cy: 120, r: 14 },
  l_wrist: { label: "Left wrist", cx: 24, cy: 155, r: 9 },
  r_wrist: { label: "Right wrist", cx: 156, cy: 155, r: 9 },
  l_hip: { label: "Left hip", cx: 70, cy: 155, r: 12 },
  r_hip: { label: "Right hip", cx: 110, cy: 155, r: 12 },
  l_quad: { label: "Left quad", cx: 72, cy: 190, r: 12 },
  r_quad: { label: "Right quad", cx: 108, cy: 190, r: 12 },
  l_knee: { label: "Left knee", cx: 74, cy: 220, r: 10 },
  r_knee: { label: "Right knee", cx: 106, cy: 220, r: 10 },
  l_shin: { label: "Left shin", cx: 74, cy: 252, r: 10 },
  r_shin: { label: "Right shin", cx: 106, cy: 252, r: 10 },
  l_ankle: { label: "Left ankle", cx: 72, cy: 282, r: 9 },
  r_ankle: { label: "Right ankle", cx: 108, cy: 282, r: 9 },
};

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

export function BodyMap({
  side,
  usedAreas,
  onZoneSelect,
  onSideChange,
}: {
  side: BodyMapSide;
  usedAreas: string[];
  onZoneSelect: (label: string) => void;
  onSideChange: (side: BodyMapSide) => void;
}) {
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const zones = side === "front" ? FRONT_ZONES : BACK_ZONES;
  const normalizedUsed = usedAreas.map((area) => area.toLowerCase());
  const hoverLabel = hoverKey ? zones[hoverKey]?.label ?? "" : "";

  return (
    <div className="body-map-panel">
      <p className="body-map-title">Tap a zone to add</p>
      <div className="body-map-svg-wrap">
        <svg viewBox="0 0 180 300" aria-label={`${side === "front" ? "Front" : "Back"} body map for injury selection`}>
          <g className="body-map-silhouette">
            <ellipse cx={90} cy={24} rx={14} ry={17} />
            <path d={SILHOUETTE_PATH} />
          </g>
          {Object.entries(zones).map(([key, zone]) => {
            const isUsed = normalizedUsed.includes(zone.label.toLowerCase());
            const isHover = hoverKey === key;

            return (
              <g key={key}>
                <circle
                  cx={zone.cx}
                  cy={zone.cy}
                  r={zone.r}
                  className={`body-map-zone ${isUsed ? "body-map-zone-used" : ""} ${isHover ? "body-map-zone-hover" : ""}`}
                  onMouseEnter={() => setHoverKey(key)}
                  onMouseLeave={() => setHoverKey(null)}
                  onClick={() => onZoneSelect(zone.label)}
                />
                {isUsed ? <circle cx={zone.cx} cy={zone.cy} r={3} className="body-map-zone-dot" /> : null}
              </g>
            );
          })}
        </svg>
      </div>
      <div className="body-map-side-toggle">
        <button
          type="button"
          className={`body-map-side-btn ${side === "front" ? "body-map-side-btn-active" : ""}`}
          onClick={() => onSideChange("front")}
        >
          Front
        </button>
        <button
          type="button"
          className={`body-map-side-btn ${side === "back" ? "body-map-side-btn-active" : ""}`}
          onClick={() => onSideChange("back")}
        >
          Back
        </button>
      </div>
      <p className="body-map-hint">{hoverLabel || "Tap a zone, or type the area manually in a card."}</p>
    </div>
  );
}
