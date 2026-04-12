import { useId } from "react";
import styles from "@/components/nutrition-pages.module.css";
import {
  type BodyweightRange,
  filterBodyweightEntriesByRange,
  formatBodyweightDate,
  formatWeight,
} from "@/lib/nutrition-bodyweight";
import type { NutritionBodyweightLogEntry } from "@/lib/types";

const RANGE_OPTIONS: BodyweightRange[] = ["7D", "30D", "All"];

function buildLinePath(points: Array<{ x: number; y: number }>): string {
  if (!points.length) return "";
  return points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
}

function buildAreaPath(
  points: Array<{ x: number; y: number }>,
  chartBottom: number,
): string {
  if (!points.length) return "";
  const first = points[0];
  const last = points[points.length - 1];
  return `${buildLinePath(points)} L ${last.x} ${chartBottom} L ${first.x} ${chartBottom} Z`;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

type NutritionBodyweightChartProps = {
  entries: NutritionBodyweightLogEntry[];
  range: BodyweightRange;
  targetWeightKg?: number | null;
  onRangeChange: (range: BodyweightRange) => void;
};

export function NutritionBodyweightChart({
  entries,
  range,
  targetWeightKg,
  onRangeChange,
}: NutritionBodyweightChartProps) {
  const uid = useId().replace(/:/g, "");
  const gradientId = `bw-area-${uid}`;
  const filteredDescending = filterBodyweightEntriesByRange(entries, range);
  const filteredAscending = [...filteredDescending].reverse();

  if (!filteredDescending.length) {
    return (
      <article className={styles.chartShell}>
        <div className={styles.chartHeader}>
          <div className={styles.chartHeaderCopy}>
            <p className="kicker">Trend chart</p>
            <h2 className="form-section-title">Weight trace</h2>
            <p className="muted">This surface will map your daily drift, target line, and recent change as soon as the first weigh-in lands.</p>
          </div>
          <div className={styles.rangeRail} aria-label="Bodyweight chart range">
            {RANGE_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={range === option}
                className={`${styles.rangeButton} ${range === option ? styles.rangeButtonActive : ""}`.trim()}
                onClick={() => onRangeChange(option)}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
        <div className={styles.chartFrame}>
          <div className={styles.chartEmpty}>
            <p className={styles.chartEmptyTitle}>No trendline yet</p>
            <p className={styles.chartEmptyBody}>
              Log the first weigh-in below to start the red trace, unlock recent-change context, and turn this panel into a useful cut monitor.
            </p>
          </div>
        </div>
      </article>
    );
  }

  const width = 1000;
  const height = 320;
  const paddingTop = 20;
  const paddingRight = 18;
  const paddingBottom = 34;
  const paddingLeft = 18;
  const chartWidth = width - paddingLeft - paddingRight;
  const chartHeight = height - paddingTop - paddingBottom;
  const chartBottom = height - paddingBottom;

  const weights = filteredAscending.map((entry) => entry.weight_kg);
  if (targetWeightKg != null) {
    weights.push(targetWeightKg);
  }

  const minWeight = Math.min(...weights);
  const maxWeight = Math.max(...weights);
  const rangeSpan = Math.max(maxWeight - minWeight, 0.6);
  const domainPadding = Math.max(rangeSpan * 0.2, 0.4);
  const domainMin = minWeight - domainPadding;
  const domainMax = maxWeight + domainPadding;
  const domainSpan = domainMax - domainMin || 1;

  function getX(index: number): number {
    if (filteredAscending.length === 1) {
      return paddingLeft + chartWidth / 2;
    }
    return paddingLeft + (index / (filteredAscending.length - 1)) * chartWidth;
  }

  function getY(weightKg: number): number {
    const ratio = (weightKg - domainMin) / domainSpan;
    const rawY = chartBottom - ratio * chartHeight;
    return clamp(rawY, paddingTop, chartBottom);
  }

  const points = filteredAscending.map((entry, index) => ({
    x: getX(index),
    y: getY(entry.weight_kg),
    entry,
  }));
  const linePath = buildLinePath(points);
  const areaPath = buildAreaPath(points, chartBottom);
  const targetY = targetWeightKg != null ? getY(targetWeightKg) : null;
  const latestEntry = filteredDescending[0];
  const highestWeight = Math.max(...filteredDescending.map((entry) => entry.weight_kg));
  const lowestWeight = Math.min(...filteredDescending.map((entry) => entry.weight_kg));
  const firstDate = filteredAscending[0]?.date ?? "";
  const lastDate = filteredAscending[filteredAscending.length - 1]?.date ?? "";

  return (
    <article className={styles.chartShell}>
      <div className={styles.chartHeader}>
        <div className={styles.chartHeaderCopy}>
          <p className="kicker">Trend chart</p>
          <h2 className="form-section-title">Weight trace</h2>
          <p className="muted">Actual log entries drive the red trend line. The target line stays subtle so the data keeps first priority.</p>
        </div>
        <div className={styles.rangeRail} aria-label="Bodyweight chart range">
          {RANGE_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={range === option}
              className={`${styles.rangeButton} ${range === option ? styles.rangeButtonActive : ""}`.trim()}
              onClick={() => onRangeChange(option)}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.chartFrame}>
        <svg
          className={styles.chartSvg}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`Bodyweight trend chart for ${range}`}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#b5122b" stopOpacity="0.38" />
              <stop offset="100%" stopColor="#b5122b" stopOpacity="0" />
            </linearGradient>
          </defs>

          {targetY != null ? (
            <>
              <line
                x1={paddingLeft}
                x2={width - paddingRight}
                y1={targetY}
                y2={targetY}
                stroke="rgba(255,255,255,0.28)"
                strokeDasharray="8 8"
                strokeWidth="1.5"
              />
              <text
                x={width - paddingRight}
                y={targetY - 14}
                fill="rgba(255,255,255,0.52)"
                fontSize="22"
                fontFamily="var(--font-mono)"
                textAnchor="end"
                letterSpacing="0.14em"
              >
                TARGET
              </text>
            </>
          ) : null}

          <text
            x={paddingLeft}
            y={paddingTop + 12}
            fill="rgba(255,255,255,0.42)"
            fontSize="22"
            fontFamily="var(--font-mono)"
            letterSpacing="0.14em"
          >
            {highestWeight.toFixed(1)} KG
          </text>
          <text
            x={paddingLeft}
            y={chartBottom - 8}
            fill="rgba(255,255,255,0.42)"
            fontSize="22"
            fontFamily="var(--font-mono)"
            letterSpacing="0.14em"
          >
            {lowestWeight.toFixed(1)} KG
          </text>

          <path d={areaPath} fill={`url(#${gradientId})`} />
          <path
            d={linePath}
            fill="none"
            stroke="var(--brand-red)"
            strokeWidth="4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {points.map((point, index) => (
            <g key={`${point.entry.date}-${point.entry.time ?? "na"}-${index}`}>
              <circle cx={point.x} cy={point.y} r="6" fill="rgba(181, 18, 43, 0.18)" />
              <circle cx={point.x} cy={point.y} r="3.2" fill="var(--brand-red)" />
            </g>
          ))}

          {firstDate && lastDate && firstDate !== lastDate ? (
            <>
              <text
                x={paddingLeft}
                y={height - 8}
                fill="rgba(255,255,255,0.42)"
                fontSize="22"
                fontFamily="var(--font-mono)"
                letterSpacing="0.12em"
              >
                {formatBodyweightDate(firstDate).toUpperCase()}
              </text>
              <text
                x={width - paddingRight}
                y={height - 8}
                fill="rgba(255,255,255,0.42)"
                fontSize="22"
                fontFamily="var(--font-mono)"
                textAnchor="end"
                letterSpacing="0.12em"
              >
                {formatBodyweightDate(lastDate).toUpperCase()}
              </text>
            </>
          ) : (
            <text
              x={width / 2}
              y={height - 8}
              fill="rgba(255,255,255,0.42)"
              fontSize="22"
              fontFamily="var(--font-mono)"
              textAnchor="middle"
              letterSpacing="0.12em"
            >
              {formatBodyweightDate(lastDate || firstDate).toUpperCase()}
            </text>
          )}
        </svg>

        <div className={styles.chartLegend}>
          <div className={styles.chartLegendItem}>
            <span className={styles.chartLegendSwatch} aria-hidden="true" />
            <p className={styles.chartLegendLabel}>Logged weight</p>
          </div>
          {targetY != null ? (
            <div className={styles.chartLegendItem}>
              <span className={styles.chartLegendSwatchMuted} aria-hidden="true" />
              <p className={styles.chartLegendLabel}>Target weight</p>
            </div>
          ) : null}
        </div>

        <div className={styles.chartStats}>
          <div className={styles.chartStat}>
            <p className={styles.chartLegendLabel}>Latest in range</p>
            <p className={styles.chartStatValue}>{formatWeight(latestEntry?.weight_kg)}</p>
          </div>
          <div className={styles.chartStat}>
            <p className={styles.chartLegendLabel}>High / low</p>
            <p className={styles.chartStatValue}>{highestWeight.toFixed(1)} / {lowestWeight.toFixed(1)} kg</p>
          </div>
          <div className={styles.chartStat}>
            <p className={styles.chartLegendLabel}>Span</p>
            <p className={styles.chartStatValue}>{formatBodyweightDate(firstDate)} - {formatBodyweightDate(lastDate)}</p>
          </div>
        </div>
      </div>
    </article>
  );
}
