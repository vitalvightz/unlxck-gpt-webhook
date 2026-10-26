"use client";

import Link from "next/link";
import { type CSSProperties, useEffect, useId, useRef, useState, useTransition } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { useOnReconnect } from "@/components/connection-status-banner";
import { SafetyNote } from "@/components/safety-note";
import { Skeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast-provider";
import { WeightTrendChart } from "@/components/weight-trend-chart";
import { getNutritionCurrent, trackProductEvent, updateNutritionCurrent } from "@/lib/api";
import { formatAppDate } from "@/lib/date-format";
import {
  type BodyweightRange,
  createBodyweightEntryKey,
  formatFastedState,
  formatWeight,
  formatWeightDelta,
  getBodyweightEntriesWithIndex,
  getBodyweightTrend,
  getLatestEffectiveWeight,
  getTargetGap,
  getTrendChange,
} from "@/lib/nutrition-bodyweight";
import { localDateValue, localTimeValue, toNumber, toUpdateRequest } from "@/lib/nutrition-workspace";
import { lockOverlayScroll } from "@/lib/overlay-scroll-lock";
import { WEIGHT_CUT_SAFETY } from "@/lib/safety-copy";
import type { NutritionBodyweightLogEntry, NutritionDerivedState, NutritionWorkspaceState } from "@/lib/types";
import sheet from "./session-details.module.css";
import progress from "./training-progress.module.css";
import summary from "./training-summary.module.css";
import styles from "./weight-tracker.module.css";

const RANGES: Array<{ value: BodyweightRange; label: string }> = [
  { value: "7D", label: "7 days" },
  { value: "30D", label: "30 days" },
  { value: "All", label: "All" },
];
const LIST_PAGE = 10;

type Editing = { mode: "new" } | { mode: "edit"; sourceIndex: number };

const plural = (count: number, noun: string) => `${count} ${noun}${count === 1 ? "" : "s"}`;

function describeGap(gap: number): { value: string; label: string; tone?: "green" } {
  if (gap === 0) return { value: "0.0 kg", label: "On target", tone: "green" };
  return { value: `${Math.abs(gap).toFixed(1)} kg`, label: gap > 0 ? "Above target" : "Under target", tone: gap < 0 ? "green" : undefined };
}

function describeDaysOut(days: number): string {
  return days === 0 ? "Today" : `${days}`;
}

/**
 * The plan's own weight-cut band, read from the API, never recalculated here.
 * Only an escalated cut (high or severe) earns a warning; the copy names who
 * should oversee it and never says how to cut.
 */
function cutWarning(derived: NutritionDerivedState): string | null {
  const band = derived.weight_cut_risk_band ?? "none";
  if (band !== "high" && band !== "severe" && !derived.weight_cut_supervision_required) return null;
  const days = derived.days_until_fight;
  const context = `${derived.weight_cut_pct.toFixed(1)}% of your bodyweight to target${days != null && days >= 0 ? ` with ${plural(days, "day")} to go` : ""}`;
  return band === "severe"
    ? `Severe weight cut: ${context}. Don't attempt this without your coach or a medical professional overseeing it.`
    : `High-strain weight cut: ${context}. A cut like this needs supervision from your coach or a qualified practitioner.`;
}

export function WeightTracker() {
  const { session, me } = useAppSession();
  const { showToast } = useToast();
  // Server-derived age band. Under-18s get no weight-cut feature, so the target
  // weight and the gap to it are not shown; the backend strips the stored value too.
  const isMinorAthlete = Boolean(me?.profile.is_minor);
  const [workspace, setWorkspace] = useState<NutritionWorkspaceState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [range, setRange] = useState<BodyweightRange>("30D");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [showAll, setShowAll] = useState(false);
  const loadFailed = !workspace && Boolean(error);
  const retryLoad = () => {
    setError(null);
    setReloadKey((key) => key + 1);
  };
  useOnReconnect(retryLoad, loadFailed);

  useEffect(() => {
    if (!session?.access_token) return;
    let active = true;
    getNutritionCurrent(session.access_token)
      .then((nextWorkspace) => {
        if (!active) return;
        void trackProductEvent(session.access_token, "nutrition_opened", "nutrition");
        setWorkspace(nextWorkspace);
      })
      .catch((loadError) => {
        if (!active) return;
        setError(loadError instanceof Error ? loadError.message : "Unable to load your weigh-ins.");
      });
    return () => {
      active = false;
    };
  }, [reloadKey, session?.access_token]);

  async function saveEntries(nextEntries: NutritionBodyweightLogEntry[]) {
    if (!session?.access_token || !workspace) throw new Error("Your session has expired. Sign in again.");
    const payload = toUpdateRequest(workspace);
    payload.nutrition_monitoring = { ...payload.nutrition_monitoring, daily_bodyweight_log: nextEntries };
    setWorkspace(await updateNutritionCurrent(session.access_token, payload));
  }

  const entries = workspace?.nutrition_monitoring.daily_bodyweight_log ?? [];
  const newestFirst = getBodyweightEntriesWithIndex(entries);
  const latest = newestFirst[0] ?? null;
  const latestWeight = workspace ? getLatestEffectiveWeight(workspace) : null;
  const targetKg = isMinorAthlete ? null : (workspace?.shared_camp_context.target_weight_kg ?? null);
  const gap = getTargetGap(latestWeight, targetKg);
  const derived = workspace?.derived ?? null;
  const average = derived?.rolling_7_day_average_weight ?? null;
  const pace = derived?.weekly_pace_kg ?? null;
  const daysOut = derived?.days_until_fight ?? null;
  const warning = derived && !isMinorAthlete ? cutWarning(derived) : null;
  const trend = getBodyweightTrend(entries, range);
  const trendChange = getTrendChange(trend);
  const keyOf = (entry: (typeof newestFirst)[number]) => createBodyweightEntryKey(entry, entry.sourceIndex);
  const selectedIndex = Math.max(0, trend.findIndex(entry => keyOf(entry) === selectedKey));
  const selected = trend.length ? trend[selectedKey ? selectedIndex : trend.length - 1] : null;
  // Change from the weigh-in before each one, across the whole log.
  const previousOf = (entry: (typeof newestFirst)[number]) => newestFirst[newestFirst.findIndex(item => item.sourceIndex === entry.sourceIndex) + 1] ?? null;
  const selectedPrevious = selected ? previousOf(selected) : null;
  // The smoothed trend for the days in range; absent from an older API.
  const trendLine = trend.length
    ? (derived?.bodyweight_trend ?? []).filter(point => point.date >= trend[0].date && point.date <= trend[trend.length - 1].date)
    : [];
  const selectedTrend = selected ? trendLine.find(point => point.date === selected.date) ?? null : null;
  const listed = showAll ? newestFirst : newestFirst.slice(0, LIST_PAGE);
  const tiles = [
    ...(gap != null ? [describeGap(gap)] : []),
    { value: average != null ? average.toFixed(1) : "--", label: "7-day average" },
    ...(pace != null ? [{ value: formatWeightDelta(pace), label: "Per week" }] : []),
    ...(daysOut != null && daysOut >= 0 ? [{ value: describeDaysOut(daysOut), label: daysOut === 0 ? "Fight day" : daysOut === 1 ? "Day to fight" : "Days to fight" }] : []),
  ];
  const editingEntry = editing?.mode === "edit" ? entries[editing.sourceIndex] ?? null : null;

  return (
    <RequireAuth>
      <section className={`panel history-screen ${styles.screen}`}>
        <header className="form-section-header">
          <p className="kicker">Nutrition</p>
          <h1 className="form-section-title">Weight tracker</h1>
          <p className="muted">Your weigh-ins and your trend toward fight weight.</p>
        </header>

        {!workspace ? (
          loadFailed ? (
            <div className="error-banner" role="alert">
              <p>{error}</p>
              <button type="button" className="error-banner-retry" onClick={retryLoad}>Retry</button>
            </div>
          ) : (
            <div className={styles.loading} aria-busy="true" aria-label="Loading weigh-ins">
              <Skeleton height={220} style={{ borderRadius: 14 }} />
              <Skeleton height={300} style={{ borderRadius: 14 }} />
            </div>
          )
        ) : (
          <>
            <section className={`history-summary ${styles.card}`} aria-label="Weight summary">
              <div className={summary.head}>
                <p className="history-summary-label">Your weight</p>
                {latest ? <span className={styles.lastLogged}>Last logged {formatAppDate(latest.date)}</span> : null}
              </div>
              {latest ? (
                <>
                  <div className={styles.headline}>
                    <strong>{latest.weight_kg.toFixed(1)}</strong>
                    <span>kg<br />{latest.is_fasted == null ? "Latest weigh-in" : `${formatFastedState(latest.is_fasted)} weigh-in`}</span>
                  </div>
                  <dl className={`history-summary-stats ${summary.stats}`} style={{ "--stat-count": tiles.length > 3 ? 2 : tiles.length } as CSSProperties}>
                    {tiles.map(tile => <div key={tile.label}><dt>{tile.label}</dt><dd data-tone={"tone" in tile ? tile.tone : undefined}>{tile.value}</dd></div>)}
                  </dl>
                  {!isMinorAthlete && targetKg == null ? (
                    <p className={progress.note}>No target weight yet. <Link href="/onboarding" className="auth-text-link">Set it in Camp Setup</Link> to see your gap.</p>
                  ) : null}
                </>
              ) : (
                <div className={styles.empty}>
                  <h2>No weigh-ins yet</h2>
                  <p className="muted">Weigh in at the same time each day, ideally in the morning after the toilet, so your trend compares like with like.</p>
                </div>
              )}
              <button type="button" className={`cta ${styles.logButton}`} onClick={() => setEditing({ mode: "new" })}>
                Log weigh-in
              </button>
            </section>

            {warning ? <SafetyNote tone="warning">{warning}</SafetyNote> : null}

            {trend.length ? (
              <section className={`history-summary ${styles.card}`} aria-label="Weight trend">
                <div className={summary.head}>
                  <h2 className={styles.sectionTitle}>Weight trend</h2>
                  <div className={summary.toggle} role="group" aria-label="Trend range">
                    {RANGES.map(item => (
                      <button key={item.value} type="button" aria-pressed={range === item.value} onClick={() => { setRange(item.value); setSelectedKey(null); }}>
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>
                {selected ? (
                  <div className={progress.selectedRecord} aria-live="polite" aria-label="Selected weigh-in">
                    <p><strong data-weight="">{formatWeight(selected.weight_kg)}</strong>
                      {selectedPrevious ? <span className={styles.change}>{formatWeightDelta(Math.round((selected.weight_kg - selectedPrevious.weight_kg) * 10) / 10)} vs previous</span> : null}</p>
                    <p className={progress.note}>{[formatAppDate(selected.date), selected.time, selected.is_fasted == null ? null : formatFastedState(selected.is_fasted), selectedTrend ? `Trend ${formatWeight(selectedTrend.trend_weight_kg)}` : null].filter(Boolean).join(" · ")}</p>
                    <button type="button" className={progress.textButton} onClick={() => setEditing({ mode: "edit", sourceIndex: selected.sourceIndex })}>Edit weigh-in <span aria-hidden="true">→</span></button>
                  </div>
                ) : null}
                <p className={progress.note}>
                  {plural(trend.length, "weigh-in")}
                  {trendChange != null ? ` · ${trendChange === 0 ? "No change" : `${trendChange < 0 ? "Down" : "Up"} ${Math.abs(trendChange).toFixed(1)} kg`} since ${formatAppDate(trend[0].date)}` : ""}
                </p>
                {trend.length >= 2 ? (
                  <WeightTrendChart trend={trend} trendLine={trendLine} targetKg={targetKg} selectedIndex={selectedKey ? selectedIndex : trend.length - 1}
                    onSelect={index => setSelectedKey(keyOf(trend[index]))} />
                ) : (
                  <p className={progress.note}>Log one more weigh-in to see your trend line.</p>
                )}
                <details className={progress.about}>
                  <summary>About these numbers</summary>
                  <p>Your weight is the scale reading you logged. Weight swings from day to day with water, food and training, so the trend line smooths those swings into an estimate of where your weight is heading. It is not an official weigh-in.</p>
                  <p>The trend, 7-day average and weekly pace use one reading per day: your earliest fasted weigh-in, or your earliest weigh-in if none was fasted.</p>
                  <p>Weekly pace appears once you have at least six weigh-in days spanning two weeks, with one in the last week.</p>
                </details>
              </section>
            ) : null}

            {newestFirst.length ? (
              <section className={styles.listSection} aria-label="Weigh-ins">
                <h2 className="history-section-title">Weigh-ins</h2>
                <ul className="history-list">
                  {listed.map(entry => {
                    const previous = previousOf(entry);
                    return (
                      <li key={keyOf(entry)} className={`history-row ${styles.row}`}>
                        <button type="button" className={styles.rowButton} aria-haspopup="dialog" onClick={() => setEditing({ mode: "edit", sourceIndex: entry.sourceIndex })}>
                          <span className={styles.rowMain}>
                            <span className="history-row-date">{formatAppDate(entry.date)}</span>
                            <span className="history-row-meta">
                              {[entry.time, entry.is_fasted == null ? null : formatFastedState(entry.is_fasted)].filter(Boolean).join(" · ") || "Weigh-in"}
                            </span>
                            {entry.notes ? <span className={styles.rowNote}>{entry.notes}</span> : null}
                          </span>
                          <span className={styles.rowSide}>
                            <strong>{formatWeight(entry.weight_kg)}</strong>
                            {previous ? <span>{formatWeightDelta(Math.round((entry.weight_kg - previous.weight_kg) * 10) / 10)}</span> : null}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
                {newestFirst.length > LIST_PAGE ? (
                  <button type="button" className="secondary-button" onClick={() => setShowAll(value => !value)}>
                    {showAll ? "Show fewer" : `Show all ${newestFirst.length} weigh-ins`}
                  </button>
                ) : null}
              </section>
            ) : null}

            <SafetyNote tone="warning">{WEIGHT_CUT_SAFETY}</SafetyNote>
          </>
        )}

        {editing && workspace ? (
          <WeighInSheet
            key={editing.mode === "edit" ? `edit-${editing.sourceIndex}` : "new"}
            entry={editingEntry}
            lastWeight={latest?.weight_kg ?? null}
            onClose={() => setEditing(null)}
            onSave={async (entry) => {
              const next = editing.mode === "edit"
                ? entries.map((item, index) => (index === editing.sourceIndex ? entry : item))
                : [...entries, entry];
              await saveEntries(next);
              setSelectedKey(null);
              setEditing(null);
              showToast(editing.mode === "edit" ? "Weigh-in updated." : "Weigh-in saved.", { tone: "success" });
            }}
            onDelete={editing.mode === "edit" ? async () => {
              await saveEntries(entries.filter((_, index) => index !== editing.sourceIndex));
              setSelectedKey(null);
              setEditing(null);
              showToast("Weigh-in deleted.", { tone: "success" });
            } : undefined}
          />
        ) : null}
      </section>
    </RequireAuth>
  );
}

type Draft = { weight: string; date: string; time: string; fasted: boolean | null; notes: string };

function WeighInSheet({ entry, lastWeight, onClose, onSave, onDelete }: {
  entry: NutritionBodyweightLogEntry | null;
  lastWeight: number | null;
  onClose: () => void;
  onSave: (entry: NutritionBodyweightLogEntry) => Promise<void>;
  onDelete?: () => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const weightInput = useRef<HTMLInputElement>(null);
  const heading = useId();
  const fieldId = useId();
  const [draft, setDraft] = useState<Draft>(() => entry ? {
    weight: String(entry.weight_kg), date: entry.date, time: entry.time ?? "", fasted: entry.is_fasted ?? null, notes: entry.notes ?? "",
  } : { weight: "", date: localDateValue(), time: localTimeValue(), fasted: null, notes: "" });
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    const release = lockOverlayScroll();
    weightInput.current?.focus({ preventScroll: true });
    return () => { element.close(); release(); };
  }, []);

  function step(by: number) {
    const base = toNumber(draft.weight) ?? lastWeight ?? 0;
    setDraft(current => ({ ...current, weight: Math.max(0, Math.round((base + by) * 10) / 10).toFixed(1) }));
  }

  function run(action: () => Promise<void>) {
    setError(null);
    startTransition(async () => {
      try {
        await action();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Couldn't save. Try again.");
      }
    });
  }

  function save() {
    const weight = toNumber(draft.weight);
    if (weight == null || weight <= 0) {
      setError("Enter your weight in kg.");
      weightInput.current?.focus();
      return;
    }
    if (!draft.date.trim()) {
      setError("Choose the date of this weigh-in.");
      return;
    }
    run(() => onSave({
      date: draft.date.trim(),
      weight_kg: weight,
      time: draft.time.trim() || null,
      is_fasted: draft.fasted,
      notes: draft.notes.trim() || null,
    }));
  }

  return (
    <dialog ref={dialog} className={sheet.dialog} aria-labelledby={heading} onCancel={event => { event.preventDefault(); if (!isPending) onClose(); }}>
      <header className={sheet.header}>
        <div>
          <p className={sheet.eyebrow}>Weight tracker</p>
          <h2 id={heading}>{entry ? "Edit weigh-in" : "Log weigh-in"}</h2>
          <p className={sheet.quiet}>{entry ? formatAppDate(entry.date) : "Same time each day keeps your trend honest."}</p>
        </div>
        <button type="button" className={sheet.close} aria-label="Close" onClick={onClose} disabled={isPending}>×</button>
      </header>
      <form className={`${sheet.body} ${styles.form}`} onSubmit={event => { event.preventDefault(); save(); }}>
        <div>
          <label htmlFor={`${fieldId}-weight`} className={styles.fieldLabel}>Weight</label>
          <div className={styles.weightField}>
            <button type="button" aria-label="Decrease by 0.1 kg" onClick={() => step(-0.1)}>−</button>
            <span className={styles.weightValue}>
              <input ref={weightInput} id={`${fieldId}-weight`} type="number" inputMode="decimal" step="0.1" min="0"
                placeholder={lastWeight != null ? lastWeight.toFixed(1) : "0.0"} value={draft.weight}
                onChange={event => setDraft(current => ({ ...current, weight: event.target.value }))} />
              <span aria-hidden="true">kg</span>
            </span>
            <button type="button" aria-label="Increase by 0.1 kg" onClick={() => step(0.1)}>+</button>
          </div>
        </div>

        <div>
          <p className={styles.fieldLabel} id={`${fieldId}-fasted`}>Before or after food?</p>
          <div className={`${summary.toggle} ${styles.fasted}`} role="group" aria-labelledby={`${fieldId}-fasted`}>
            {([[true, "Fasted"], [false, "Fed"]] as const).map(([value, label]) => (
              <button key={label} type="button" aria-pressed={draft.fasted === value}
                onClick={() => setDraft(current => ({ ...current, fasted: current.fasted === value ? null : value }))}>
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className={styles.when}>
          <div className="field">
            <label htmlFor={`${fieldId}-date`}>Date</label>
            <input id={`${fieldId}-date`} type="date" value={draft.date} onChange={event => setDraft(current => ({ ...current, date: event.target.value }))} />
          </div>
          <div className="field">
            <label htmlFor={`${fieldId}-time`}>Time</label>
            <input id={`${fieldId}-time`} type="time" value={draft.time} onChange={event => setDraft(current => ({ ...current, time: event.target.value }))} />
          </div>
        </div>

        <div className="field">
          <label htmlFor={`${fieldId}-notes`}>Notes <span className="muted">(optional)</span></label>
          <textarea id={`${fieldId}-notes`} rows={2} value={draft.notes} onChange={event => setDraft(current => ({ ...current, notes: event.target.value }))} />
        </div>

        {error ? <p className={styles.formError} role="alert">{error}</p> : null}

        <div className={styles.actions}>
          <button type="submit" className="cta" disabled={isPending}>{isPending ? "Saving…" : entry ? "Save changes" : "Save weigh-in"}</button>
          {onDelete ? (
            <button type="button" className="ghost-button danger-button" disabled={isPending}
              onClick={() => { if (window.confirm("Delete this weigh-in?")) run(onDelete); }}>
              Delete weigh-in
            </button>
          ) : null}
        </div>
      </form>
    </dialog>
  );
}
