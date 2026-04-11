"use client";

import { useState } from "react";

import {
  BODY_AREA_REGIONS,
  BODY_AREA_SHORTCUTS,
  findBodyAreaRegion,
  type BodyAreaMapSide,
  type BodyAreaRegionShape,
} from "@/lib/body-area-regions";

type BodyAreaMapProps = {
  side: BodyAreaMapSide;
  selectedArea: string;
  usedAreas: string[];
  targetLabel: string;
  onSideChange: (side: BodyAreaMapSide) => void;
  onSelectArea: (label: string) => void;
  onClearArea: () => void;
  onTypeManually: () => void;
};

function renderRegionShape(shape: BodyAreaRegionShape, key: string, className: string) {
  if (shape.type === "path") {
    return (
      <path
        key={key}
        className={className}
        d={shape.d}
        fillRule={shape.fillRule}
        clipRule={shape.clipRule}
        transform={shape.transform}
      />
    );
  }

  if (shape.type === "ellipse") {
    return (
      <ellipse
        key={key}
        className={className}
        cx={shape.cx}
        cy={shape.cy}
        rx={shape.rx}
        ry={shape.ry}
        transform={shape.transform}
      />
    );
  }

  return (
    <rect
      key={key}
      className={className}
      x={shape.x}
      y={shape.y}
      width={shape.width}
      height={shape.height}
      rx={shape.rx}
      ry={shape.ry}
      transform={shape.transform}
    />
  );
}

export function BodyAreaMap({
  side,
  selectedArea,
  usedAreas,
  targetLabel,
  onSideChange,
  onSelectArea,
  onClearArea,
  onTypeManually,
}: BodyAreaMapProps) {
  const [hoveredRegionId, setHoveredRegionId] = useState<string | null>(null);
  const selectedRegion = findBodyAreaRegion(selectedArea, side) ?? findBodyAreaRegion(selectedArea);
  const selectedLabel = selectedArea.trim() || "None yet";
  const currentRegions = BODY_AREA_REGIONS[side];
  const hoveredRegion = currentRegions.find((region) => region.id === hoveredRegionId) ?? null;
  const usedRegionIds = usedAreas
    .map((area) => findBodyAreaRegion(area, side) ?? findBodyAreaRegion(area))
    .filter((region): region is NonNullable<typeof region> => Boolean(region))
    .map((region) => region.id);

  return (
    <div className="body-area-map" data-side={side}>
      <div className="body-area-map-header">
        <div className="body-area-map-copy">
          <p className="label">Body area</p>
          <h3 className="body-area-map-heading">Pick the exact location</h3>
          <p className="body-area-map-description">Selections apply directly to {targetLabel}. Manual entry stays available if the exact wording needs adjusting.</p>
        </div>
        <div className="body-area-map-side-toggle" role="tablist" aria-label="Choose body map side">
          <button
            type="button"
            role="tab"
            aria-selected={side === "front"}
            className={`body-area-map-side-btn ${side === "front" ? "body-area-map-side-btn-active" : ""}`.trim()}
            onClick={() => onSideChange("front")}
          >
            Front
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={side === "back"}
            className={`body-area-map-side-btn ${side === "back" ? "body-area-map-side-btn-active" : ""}`.trim()}
            onClick={() => onSideChange("back")}
          >
            Back
          </button>
        </div>
      </div>

      <div className="body-area-map-status" aria-live="polite">
        <div className="body-area-map-chip">
          <span className="body-area-map-chip-label">Selected</span>
          <span className="body-area-map-chip-value">{selectedLabel}</span>
        </div>
        <div className="body-area-map-chip body-area-map-chip-subtle">
          <span className="body-area-map-chip-label">Editing</span>
          <span className="body-area-map-chip-value">{targetLabel}</span>
        </div>
        {hoveredRegion ? (
          <div className="body-area-map-chip body-area-map-chip-preview">
            <span className="body-area-map-chip-label">Preview</span>
            <span className="body-area-map-chip-value">{hoveredRegion.label}</span>
          </div>
        ) : null}
      </div>

      <div className="body-area-map-figure-shell">
        <svg className="body-area-map-figure" viewBox="0 0 260 580" aria-label={`${side === "front" ? "Front" : "Back"} body area map`}>
          {currentRegions.map((region) => {
            const isSelected = selectedRegion?.id === region.id;
            const isUsed = usedRegionIds.includes(region.id) && !isSelected;
            const regionClassName = [
              "body-area-map-region",
              isSelected ? "body-area-map-region-selected" : "",
              isUsed ? "body-area-map-region-used" : "",
            ]
              .filter(Boolean)
              .join(" ");

            return (
              <g
                key={region.id}
                className={regionClassName}
                role="button"
                tabIndex={0}
                aria-label={region.label}
                aria-pressed={isSelected}
                onMouseEnter={() => setHoveredRegionId(region.id)}
                onMouseLeave={() => setHoveredRegionId((current) => (current === region.id ? null : current))}
                onFocus={() => setHoveredRegionId(region.id)}
                onBlur={() => setHoveredRegionId((current) => (current === region.id ? null : current))}
                onClick={() => onSelectArea(region.label)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectArea(region.label);
                  }
                }}
              >
                <title>{region.label}</title>
                {region.shapes.map((shape, shapeIndex) =>
                  renderRegionShape(shape, `${region.id}-${String(shapeIndex)}`, "body-area-map-region-shape"),
                )}
              </g>
            );
          })}
        </svg>
      </div>

      <div className="body-area-map-footer">
        <div className="body-area-map-preview">
          <span className="body-area-map-preview-label">{hoveredRegion ? "Hovering" : "Tip"}</span>
          <span className="body-area-map-preview-value">
            {hoveredRegion ? hoveredRegion.label : "Hover or focus a region to preview it, then click to set the pain area."}
          </span>
        </div>
        <div className="body-area-map-actions">
          <button type="button" className="body-area-map-action" onClick={onClearArea} disabled={!selectedArea.trim()}>
            Clear
          </button>
          <button type="button" className="body-area-map-action" onClick={onTypeManually}>
            Type manually
          </button>
        </div>
      </div>

      <div className="body-area-map-shortcuts">
        <p className="body-area-map-shortcuts-label">Common areas</p>
        <div className="body-area-map-shortcuts-grid">
          {BODY_AREA_SHORTCUTS.map((shortcut) => (
            <button
              key={shortcut.id}
              type="button"
              className="body-area-map-shortcut"
              onClick={() => {
                const nextSide = "side" in shortcut ? shortcut.side : undefined;
                if (nextSide) {
                  onSideChange(nextSide);
                }
                onSelectArea(shortcut.value);
              }}
            >
              {shortcut.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
