"use client";

import { useEffect, useState, useTransition } from "react";

import { NutritionBodyweightChart } from "@/components/nutrition-bodyweight-chart";
import styles from "@/components/nutrition-pages.module.css";
import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { NutritionSubnav } from "@/components/nutrition-subnav";
import { NutritionWorkspaceHeader } from "@/components/nutrition-workspace-header";
import { getNutritionCurrent, updateNutritionCurrent } from "@/lib/api";
import {
  type BodyweightRange,
  createBodyweightEntryKey,
  formatBodyweightDate,
  formatBodyweightTime,
  formatFastedState,
  formatTargetGapLabel,
  formatWeight,
  formatWeightDelta,
  getBodyMassIndex,
  getBodyweightEntriesWithIndex,
  getLatestBodyweightEntry,
  getLatestEffectiveWeight,
  getPreviousBodyweightEntry,
  getRecentChange,
  getSevenDayAverage,
  getTargetGap,
} from "@/lib/nutrition-bodyweight";
import { localDateValue, localTimeValue, toNumber, toUpdateRequest } from "@/lib/nutrition-workspace";
import type { NutritionBodyweightLogEntry, NutritionWorkspaceState, WeightSource } from "@/lib/types";

type FastedSelection = "unset" | "fasted" | "fed";

type BodyweightDraft = {
  date: string;
  is_fasted: FastedSelection;
  notes: string;
  time: string;
  weight_kg: string;
};

const FASTED_OPTIONS: Array<{ label: string; value: FastedSelection }> = [
  { label: "Unset", value: "unset" },
  { label: "Fasted", value: "fasted" },
  { label: "Fed", value: "fed" },
];

function fastedSelectionFromValue(value: boolean | null | undefined): FastedSelection {
  if (value === true) return "fasted";
  if (value === false) return "fed";
  return "unset";
}

function fastedValueFromSelection(value: FastedSelection): boolean | null {
  if (value === "fasted") return true;
  if (value === "fed") return false;
  return null;
}

function createEmptyDraft(): BodyweightDraft {
  return {
    date: localDateValue(),
    is_fasted: "unset",
    notes: "",
    time: localTimeValue(),
    weight_kg: "",
  };
}

function createDraftFromEntry(entry: NutritionBodyweightLogEntry): BodyweightDraft {
  return {
    date: entry.date,
    is_fasted: fastedSelectionFromValue(entry.is_fasted),
    notes: entry.notes ?? "",
    time: entry.time ?? "",
    weight_kg: String(entry.weight_kg),
  };
}

function createEntryFromDraft(draft: BodyweightDraft): NutritionBodyweightLogEntry {
  const date = draft.date.trim();
  const weight = toNumber(draft.weight_kg);
  const time = draft.time.trim();
  const notes = draft.notes.trim();

  if (!date) {
    throw new Error("Date is required.");
  }
  if (weight == null || weight <= 0) {
    throw new Error("Weight must be a positive number.");
  }

  return {
    date,
    is_fasted: fastedValueFromSelection(draft.is_fasted),
    notes: notes || null,
    time: time || null,
    weight_kg: weight,
  };
}

function formatWeightSource(value: WeightSource | null | undefined): string {
  if (value === "latest_bodyweight_log") return "Latest log";
  if (value === "manual") return "Manual";
  if (value === "imported") return "Imported";
  return "Unspecified";
}

function formatBmiValue(value: number | null): string {
  if (value == null) return "--";
  return value.toFixed(1);
}

export function BodyweightLogScreen() {
  const { session, me } = useAppSession();
  const [workspace, setWorkspace] = useState<NutritionWorkspaceState | null>(null);
  const [selectedRange, setSelectedRange] = useState<BodyweightRange>("30D");
  const [quickAdd, setQuickAdd] = useState<BodyweightDraft>(() => createEmptyDraft());
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editingDraft, setEditingDraft] = useState<BodyweightDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    if (!session?.access_token) return;
    let active = true;
    getNutritionCurrent(session.access_token)
      .then((nextWorkspace) => {
        if (!active) return;
        setWorkspace(nextWorkspace);
      })
      .catch((loadError) => {
        if (!active) return;
        setError(loadError instanceof Error ? loadError.message : "Unable to load bodyweight log.");
      });
    return () => {
      active = false;
    };
  }, [session?.access_token]);

  const athleteName = me?.profile.full_name || me?.profile.email || "Nutrition workspace";
  const entries = workspace?.nutrition_monitoring.daily_bodyweight_log ?? [];
  const indexedEntries = getBodyweightEntriesWithIndex(entries);
  const latestEntry = workspace ? getLatestBodyweightEntry(entries) : null;
  const previousEntry = workspace ? getPreviousBodyweightEntry(entries) : null;
  const latestEffectiveWeight = workspace ? getLatestEffectiveWeight(workspace) : null;
  const sevenDayAverage = workspace ? getSevenDayAverage(entries) : null;
  const bmi = workspace ? getBodyMassIndex(workspace.nutrition_profile.height_cm ?? null, latestEffectiveWeight) : null;
  const targetGap = workspace ? getTargetGap(latestEffectiveWeight, workspace.shared_camp_context.target_weight_kg) : null;
  const recentChange = workspace ? getRecentChange(entries, selectedRange) : null;

  function persistEntries(nextEntries: NutritionBodyweightLogEntry[], successMessage: string, onSuccess?: () => void) {
    if (!session?.access_token || !workspace) return;
    setError(null);
    setMessage(null);

    const nextPayload = toUpdateRequest(workspace);
    nextPayload.nutrition_monitoring = {
      ...nextPayload.nutrition_monitoring,
      daily_bodyweight_log: nextEntries,
    };

    startTransition(async () => {
      try {
        const nextWorkspace = await updateNutritionCurrent(session.access_token, nextPayload);
        setWorkspace(nextWorkspace);
        setMessage(successMessage);
        onSuccess?.();
      } catch (saveError) {
        setError(saveError instanceof Error ? saveError.message : "Unable to save bodyweight log.");
      }
    });
  }

  function handleQuickAddSave() {
    try {
      const nextEntry = createEntryFromDraft(quickAdd);
      persistEntries([...entries, nextEntry], "Bodyweight entry saved.", () => {
        setQuickAdd(createEmptyDraft());
      });
    } catch (draftError) {
      setError(draftError instanceof Error ? draftError.message : "Unable to save bodyweight entry.");
      setMessage(null);
    }
  }

  function startEditing(entry: NutritionBodyweightLogEntry, sourceIndex: number) {
    setEditingKey(createBodyweightEntryKey(entry, sourceIndex));
    setEditingDraft(createDraftFromEntry(entry));
    setError(null);
    setMessage(null);
  }

  function cancelEditing() {
    setEditingKey(null);
    setEditingDraft(null);
  }

  function handleEditSave(sourceIndex: number) {
    if (!editingDraft || !workspace) return;

    try {
      const nextEntry = createEntryFromDraft(editingDraft);
      const nextEntries = workspace.nutrition_monitoring.daily_bodyweight_log.map((entry, index) =>
        index === sourceIndex ? nextEntry : entry,
      );
      persistEntries(nextEntries, "Bodyweight entry updated.", () => {
        setEditingKey(null);
        setEditingDraft(null);
      });
    } catch (draftError) {
      setError(draftError instanceof Error ? draftError.message : "Unable to update bodyweight entry.");
      setMessage(null);
    }
  }

  function handleDelete(sourceIndex: number) {
    if (!workspace) return;
    const confirmed = window.confirm("Delete this weigh-in entry?");
    if (!confirmed) return;

    const nextEntries = workspace.nutrition_monitoring.daily_bodyweight_log.filter((_, index) => index !== sourceIndex);
    persistEntries(nextEntries, "Bodyweight entry deleted.", () => {
      if (editingDraft && editingKey) {
        setEditingDraft(null);
        setEditingKey(null);
      }
    });
  }

  return (
    <RequireAuth>
      <section className={`panel ${styles.bodyweightPage}`}>
        <NutritionWorkspaceHeader
          athleteName={athleteName}
          title="Bodyweight log"
          description="A dedicated fight-lab surface for daily weigh-ins, fasted context, disciplined trend review, and explicit history edits."
        />
        <NutritionSubnav />

        {!workspace ? (
          <section className="support-panel loading-card"><p className="muted">Loading bodyweight log.</p></section>
        ) : (
          <>
            <section className={styles.heroPanel}>
              <div className={styles.heroHeader}>
                <div className={styles.heroHeaderCopy}>
                  <p className="kicker">Latest readout</p>
                  <h2 className="form-section-title">Current trace</h2>
                  <p className="muted">The hero locks onto the latest logged number so weight stays the loudest signal on the page.</p>
                </div>
              </div>

              <div className={styles.heroBody}>
                <div className={styles.heroWeightRow}>
                  <p className={`${styles.heroWeight} ${latestEntry ? "" : styles.heroWeightEmpty}`.trim()}>
                    {latestEntry ? latestEntry.weight_kg.toFixed(1) : "Await first weigh-in"}
                  </p>
                  {latestEntry ? <p className={styles.heroUnit}>KG</p> : null}
                </div>

                <div className={styles.heroMetaGrid}>
                  <div className={styles.heroMetaCard}>
                    <p className={styles.heroMetaLabel}>Last entry</p>
                    <p className={styles.heroMetaValue}>{formatBodyweightDate(latestEntry?.date ?? null)}</p>
                  </div>
                  <div className={styles.heroMetaCard}>
                    <p className={styles.heroMetaLabel}>Target</p>
                    <p className={styles.heroMetaValue}>{formatWeight(workspace.shared_camp_context.target_weight_kg ?? null)}</p>
                  </div>
                  <div className={styles.heroMetaCard}>
                    <p className={styles.heroMetaLabel}>Weight source</p>
                    <p className={styles.heroMetaValue}>{formatWeightSource(workspace.shared_camp_context.current_weight_source)}</p>
                  </div>
                </div>
              </div>
            </section>

            <section className={styles.kpiRail}>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>BMI</p>
                <p className={styles.kpiValue}>{formatBmiValue(bmi)}</p>
                <p className={styles.kpiHelper}>
                  {bmi == null ? "Needs height and effective weight." : "Derived from saved height and effective current weight."}
                </p>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>7-day average</p>
                <p className={styles.kpiValue}>{formatWeight(sevenDayAverage)}</p>
                <p className={styles.kpiHelper}>Calculated from the seven most recent logged entries.</p>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Target gap</p>
                <p className={styles.kpiValue}>{formatTargetGapLabel(targetGap)}</p>
                <p className={styles.kpiHelper}>
                  {targetGap == null ? "Add a target weight in the workspace." : "Gap between effective weight and saved target."}
                </p>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>Recent change</p>
                <p className={styles.kpiValue}>{formatWeightDelta(recentChange)}</p>
                <p className={styles.kpiHelper}>
                  {recentChange == null
                    ? "Needs two entries inside the selected range."
                    : `Latest entry vs previous entry inside ${selectedRange}.`}
                </p>
              </article>
            </section>

            <NutritionBodyweightChart
              entries={entries}
              range={selectedRange}
              targetWeightKg={workspace.shared_camp_context.target_weight_kg ?? null}
              onRangeChange={setSelectedRange}
            />

            <section className={styles.quickAddShell}>
              <div className={styles.moduleHeader}>
                <div className={styles.moduleHeaderCopy}>
                  <p className="kicker">Quick add</p>
                  <h2 className="form-section-title">New weigh-in</h2>
                  <p className="muted">Entry-first flow: lock the number, add fasted context and notes, then save the log immediately.</p>
                </div>
              </div>

              <div className={styles.quickAddGrid}>
                <div className={`field ${styles.quickWeightField}`}>
                  <label>Weight (kg)</label>
                  <input
                    type="number"
                    inputMode="decimal"
                    step="0.1"
                    placeholder="72.4"
                    value={quickAdd.weight_kg}
                    onChange={(event) => setQuickAdd((current) => ({ ...current, weight_kg: event.target.value }))}
                  />
                </div>

                <div className={styles.quickMetaGrid}>
                  <div className="field">
                    <label>Date</label>
                    <input
                      type="date"
                      value={quickAdd.date}
                      onChange={(event) => setQuickAdd((current) => ({ ...current, date: event.target.value }))}
                    />
                  </div>
                  <div className="field">
                    <label>Time</label>
                    <input
                      type="time"
                      value={quickAdd.time}
                      onChange={(event) => setQuickAdd((current) => ({ ...current, time: event.target.value }))}
                    />
                  </div>
                  <div className="field">
                    <label>Fasted state</label>
                    <div className={styles.stateRail} aria-label="Quick add fasted state">
                      {FASTED_OPTIONS.map((option) => (
                        <button
                          key={option.value}
                          type="button"
                          aria-pressed={quickAdd.is_fasted === option.value}
                          className={`${styles.stateButton} ${quickAdd.is_fasted === option.value ? styles.stateButtonActive : ""}`.trim()}
                          onClick={() => setQuickAdd((current) => ({ ...current, is_fasted: option.value }))}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className={`field ${styles.quickNotes}`}>
                    <label>Notes</label>
                    <textarea
                      rows={3}
                      value={quickAdd.notes}
                      onChange={(event) => setQuickAdd((current) => ({ ...current, notes: event.target.value }))}
                    />
                  </div>
                </div>
              </div>

              <div className={styles.quickFooter}>
                <p className="muted">Latest source behavior stays untouched. If the newest logged weight matches the effective current weight, the existing backend logic still marks it as log-driven.</p>
                <button type="button" className="cta" onClick={handleQuickAddSave} disabled={isPending}>
                  {isPending ? "Saving..." : "Save entry"}
                </button>
              </div>
            </section>

            <section className={styles.historyShell}>
              <div className={styles.historyHeaderBar}>
                <div className={styles.moduleHeaderCopy}>
                  <p className="kicker">History</p>
                  <h2 className="form-section-title">Editable entries</h2>
                  <p className="muted">Reverse chronological with explicit save affordances so changes are always deliberate.</p>
                </div>
              </div>

              {indexedEntries.length ? (
                <div className={styles.historyList}>
                  {indexedEntries.map((entry) => {
                    const cardKey = createBodyweightEntryKey(entry, entry.sourceIndex);
                    const isEditing = editingKey === cardKey && editingDraft != null;
                    return (
                      <article
                        key={cardKey}
                        className={`${styles.historyCard} ${isEditing ? styles.historyCardEditing : ""}`.trim()}
                      >
                        <div className={styles.historyHeader}>
                          <div className={styles.historyPrimary}>
                            <p className={styles.historyDate}>{formatBodyweightDate(entry.date)}</p>
                            <p className={styles.historyWeight}>{entry.weight_kg.toFixed(1)} kg</p>
                            <div className={styles.historyMetaRow}>
                              <span className={styles.historyMetaTag}>{formatBodyweightTime(entry.time)}</span>
                              <span className={styles.historyMetaTag}>{formatFastedState(entry.is_fasted)}</span>
                              <span className={styles.historyMetaTag}>
                                {latestEntry && latestEntry.date === entry.date && latestEntry.time === entry.time && latestEntry.weight_kg === entry.weight_kg
                                  ? "Latest"
                                  : previousEntry && previousEntry.date === entry.date && previousEntry.time === entry.time && previousEntry.weight_kg === entry.weight_kg
                                    ? "Previous"
                                    : `Entry ${entry.sourceIndex + 1}`}
                              </span>
                            </div>
                          </div>

                          <div className={styles.historyActions}>
                            <button
                              type="button"
                              className="ghost-button"
                              onClick={() => startEditing(entry, entry.sourceIndex)}
                              disabled={isPending}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              className="ghost-button danger-button"
                              onClick={() => handleDelete(entry.sourceIndex)}
                              disabled={isPending}
                            >
                              Delete
                            </button>
                          </div>
                        </div>

                        {entry.notes ? <p className={styles.historyNotes}>{entry.notes}</p> : null}

                        {isEditing ? (
                          <div className={styles.historyEditor}>
                            <div className={styles.historyEditorGrid}>
                              <div className="field">
                                <label>Date</label>
                                <input
                                  type="date"
                                  value={editingDraft.date}
                                  onChange={(event) =>
                                    setEditingDraft((current) => current ? { ...current, date: event.target.value } : current)
                                  }
                                />
                              </div>
                              <div className="field">
                                <label>Weight (kg)</label>
                                <input
                                  type="number"
                                  step="0.1"
                                  value={editingDraft.weight_kg}
                                  onChange={(event) =>
                                    setEditingDraft((current) => current ? { ...current, weight_kg: event.target.value } : current)
                                  }
                                />
                              </div>
                              <div className="field">
                                <label>Time</label>
                                <input
                                  type="time"
                                  value={editingDraft.time}
                                  onChange={(event) =>
                                    setEditingDraft((current) => current ? { ...current, time: event.target.value } : current)
                                  }
                                />
                              </div>
                              <div className="field">
                                <label>Fasted state</label>
                                <div className={styles.stateRail} aria-label="Edit fasted state">
                                  {FASTED_OPTIONS.map((option) => (
                                    <button
                                      key={option.value}
                                      type="button"
                                      aria-pressed={editingDraft.is_fasted === option.value}
                                      className={`${styles.stateButton} ${editingDraft.is_fasted === option.value ? styles.stateButtonActive : ""}`.trim()}
                                      onClick={() =>
                                        setEditingDraft((current) => current ? { ...current, is_fasted: option.value } : current)
                                      }
                                    >
                                      {option.label}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            </div>

                            <div className="field">
                              <label>Notes</label>
                              <textarea
                                rows={3}
                                value={editingDraft.notes}
                                onChange={(event) =>
                                  setEditingDraft((current) => current ? { ...current, notes: event.target.value } : current)
                                }
                              />
                            </div>

                            <div className={styles.historyActions}>
                              <button type="button" className="cta" onClick={() => handleEditSave(entry.sourceIndex)} disabled={isPending}>
                                {isPending ? "Saving..." : "Save changes"}
                              </button>
                              <button type="button" className="ghost-button" onClick={cancelEditing} disabled={isPending}>
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : null}
                      </article>
                    );
                  })}
                </div>
              ) : (
                <div className={styles.historyEmpty}>
                  <p className={styles.historyEmptyTitle}>No logged history yet</p>
                  <p className={styles.softMeta}>The full structure is ready. Add the first weigh-in above and this list will switch into reverse-chronological history with inline edits and deletes.</p>
                </div>
              )}
            </section>
          </>
        )}

        {message ? <div className="success-banner athlete-motion-slot athlete-motion-status">{message}</div> : null}
        {error ? <div className="error-banner athlete-motion-slot athlete-motion-status">{error}</div> : null}
      </section>
    </RequireAuth>
  );
}
