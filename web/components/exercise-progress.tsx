"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ExercisePerformance, PersonalExercise } from "@/lib/api-schema.generated";
import { formatAppDate } from "@/lib/date-format";
import { detailMeasurements } from "@/lib/session-details";
import { measurementBasis, measurementCount, progressPoints, progressSeries } from "@/lib/exercise-progress";
import styles from "./training-progress.module.css";

export function ExerciseProgress({ records, exercise, hasMore, onInspect }: {
  records: ExercisePerformance[]; exercise: PersonalExercise; hasMore: boolean; onInspect: (id: string) => void;
}) {
  const options = useMemo(() => progressSeries(records), [records]);
  const [seriesId, setSeriesId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const series = options.find(option => option.id === seriesId) ?? options[0];
  // Only eligible measurements: axis, path, count, selection and best all derive from this set.
  const valid = useMemo(() => series ? progressPoints(records, series) : [], [records, series]);
  const plot = useRef<HTMLDivElement>(null);
  const [plotWidth, setPlotWidth] = useState(600);
  const chartVisible = valid.length >= 3;
  useEffect(() => {
    const element = plot.current;
    if (!element) return;
    const observer = new ResizeObserver(entries => setPlotWidth(Math.max(24, entries[0].contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, [chartVisible]);
  const selected = valid.find(point => point.record.id === selectedId) ?? valid.at(-1);
  const selectedIndex = valid.findIndex(point => point.record.id === selected?.record.id);
  const values = valid.map(point => point.value);
  const max = Math.max(...values), min = Math.min(...values);
  const highestPoint = valid.findLast(point => point.value === max);
  const padding = Math.max((max - min) * .2, max * .05, 1);
  const floor = Math.max(0, min - padding), ceiling = max + padding;
  const firstDay = valid[0]?.record.training_day, lastDay = valid.at(-1)?.record.training_day;
  const start = Date.parse(firstDay ?? ""), span = Date.parse(lastDay ?? "") - start;
  const x = (day: string) => span ? 12 + (Date.parse(day) - start) / span * (plotWidth - 24) : plotWidth / 2;
  const y = (value: number) => 180 - (value - floor) / (ceiling - floor) * 160;
  // Irregular dates without records do not invent samples.
  const path = valid.map((point, index) => `${index ? "L" : "M"}${x(point.record.training_day).toFixed(2)},${y(point.value).toFixed(2)}`).join(" ");
  const format = (value: number) => `${Number(value.toFixed(2))} ${series?.unit}`;
  const best = series?.metric === "load" ? exercise.best_loads.find(load => load.unit === series.unit)?.value : undefined;
  return <section className={styles.exerciseChart} aria-label="Exercise progress">
    {series?.metric === "load" && records.some(record => record.performed_values?.set_entries?.length) ? <p className={styles.note}>Load shows the heaviest recorded set in each session.</p> : null}
    <div className={styles.sectionHead}><h3>Recorded performance</h3>
      {options.length > 1 ? <label className={styles.selectLabel}>Measurement<select aria-label="Progress measurement" value={series.id} onChange={event => { setSeriesId(event.target.value); setSelectedId(null); }}>
        {options.map(option => <option key={option.id} value={option.id}>{option.label}{option.unit !== option.metric ? ` · ${option.unit}` : ""}</option>)}
      </select></label> : series ? <span className={styles.note}>{series.label} · {series.unit}</span> : null}
    </div>
    {!selected ? <p className={styles.note}>No comparable measurements in the loaded records.{hasMore ? " Load earlier performances to check older records." : ""}</p> : <>
      <div className={styles.headline}><strong>{selected.value}</strong><span>{series.unit}<br />{formatAppDate(selected.record.training_day)}</span></div>
      <p className={styles.note}>{measurementCount(valid.length, series.metric)}{hasMore ? " · Earlier records available" : ""}.</p>
      {valid.length >= 3 ? <>
        <div ref={plot} className={styles.linePlot} onPointerDown={event => {
          const bounds = event.currentTarget.getBoundingClientRect();
          const choose = (clientX: number, clientY: number) => {
            const px = (clientX - bounds.left) / bounds.width * plotWidth;
            const py = (clientY - bounds.top) / bounds.height * 200;
            const nearest = valid.reduce((a, b) => Math.hypot(x(a.record.training_day) - px, y(a.value) - py) <= Math.hypot(x(b.record.training_day) - px, y(b.value) - py) ? a : b);
            setSelectedId(nearest.record.id);
          };
          choose(event.clientX, event.clientY);
          if (event.pointerType === "mouse") event.currentTarget.setPointerCapture(event.pointerId);
        }} onPointerMove={event => {
          if (event.buttons !== 1 || event.pointerType !== "mouse") return;
          const bounds = event.currentTarget.getBoundingClientRect();
          const px = (event.clientX - bounds.left) / bounds.width * plotWidth;
          const nearest = valid.reduce((a, b) => Math.abs(x(a.record.training_day) - px) <= Math.abs(x(b.record.training_day) - px) ? a : b);
          setSelectedId(nearest.record.id);
        }}>
          <svg viewBox={`0 0 ${plotWidth} 200`} preserveAspectRatio="none" aria-hidden="true">
            {[20, 100, 180].map(value => <line key={value} x1="0" x2={plotWidth} y1={value} y2={value} className={styles.lineGrid} />)}
            <path d={path} className={styles.line} />
            {valid.map(point => <g key={point.record.id}>
              {point === highestPoint ? <circle cx={x(point.record.training_day)} cy={y(point.value)} r="8" className={styles.point} /> : null}
              <circle cx={x(point.record.training_day)} cy={y(point.value)} r={selected.record.id === point.record.id ? 5 : 3} className={selected.record.id === point.record.id ? styles.activePoint : styles.point} />
            </g>)}
          </svg>
          <span className={styles.yTop}>{Number(ceiling.toFixed(1))}</span><span className={styles.yBottom}>{Number(floor.toFixed(1))}</span>
        </div>
        <div className={styles.dateAxis}><span>{formatAppDate(firstDay)}</span><span>{formatAppDate(lastDay)}</span></div>
        <div className={styles.scrub}>
          <button type="button" aria-label="Previous performance" disabled={selectedIndex <= 0} onClick={() => setSelectedId(valid[selectedIndex - 1].record.id)}>‹</button>
          <input type="range" aria-label="Inspect performance" aria-valuetext={`${formatAppDate(selected.record.training_day)}: ${format(selected.value)}`} min={0} max={valid.length - 1} value={selectedIndex} onChange={event => setSelectedId(valid[Number(event.target.value)].record.id)} />
          <button type="button" aria-label="Next performance" disabled={selectedIndex >= valid.length - 1} onClick={() => setSelectedId(valid[selectedIndex + 1].record.id)}>›</button>
        </div>
        <p className={styles.note}>{max === best ? "Best recorded load" : "Highest shown"}: {format(max)}. {series.metric === "load" ? "Different sets and reps are not equivalent strength performances." : ""}</p>
      </> : valid.length === 2 ? <div className={styles.twoRecords}>{valid.map(point => <button key={point.record.id} type="button" aria-pressed={selected.record.id === point.record.id} onClick={() => setSelectedId(point.record.id)}>
        <span>{formatAppDate(point.record.training_day)}</span><strong>{format(point.value)}</strong><span>Inspect performance</span>
      </button>)}</div> : null}
      <div className={styles.selectedRecord} aria-live="polite" aria-label="Selected performance">
        <strong>{format(selected.value)}</strong><p className={styles.note}>{formatAppDate(selected.record.training_day)} · {measurementBasis(selected.record, series.metric)}</p>
        <p className={styles.note}>{detailMeasurements(selected.record.performed_values as Record<string, unknown>).map(item => `${item.label}: ${item.value}`).join(" · ")}</p>
        <button type="button" className={styles.textButton} onClick={() => onInspect(selected.record.id)}>View original performance <span aria-hidden="true">↓</span></button>
      </div>
    </>}
  </section>;
}
