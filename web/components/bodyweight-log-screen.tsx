"use client";

import { useEffect, useState, useTransition } from "react";

import { NutritionBodyweightChart } from "@/components/nutrition-bodyweight-chart";
import styles from "@/components/nutrition-pages.module.css";
import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { EmptyState } from "@/components/empty-state";
import { NutritionSubnav } from "@/components/nutrition-subnav";
import { NutritionWorkspaceHeader } from "@/components/nutrition-workspace-header";
import { SafetyNote } from "@/components/safety-note";
import { getNutritionCurrent, updateNutritionCurrent } from "@/lib/api";
import { WEIGHT_CUT_SAFETY } from "@/lib/safety-copy";
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
import { useTranslations as useAppTranslations } from "next-intl";
import { translateUiText } from "@/i18n/ui-text";


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
    const appText = useAppTranslations("AppText");
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

  const athleteName = me?.profile.full_name || me?.profile.email || appText("text_02207fbaeaef");
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
          title={appText("text_c6284ea16536")}
          description={appText("text_e0b800f927f0")}
        />
        <NutritionSubnav />
        <SafetyNote tone="warning">{WEIGHT_CUT_SAFETY}</SafetyNote>

        {!workspace ? (
          <section className="support-panel loading-card"><p className="muted">{appText("text_1f23d4d3f810")}</p></section>
        ) : (
          <>
            <section className={styles.heroPanel}>
              <div className={styles.heroHeader}>
                <div className={styles.heroHeaderCopy}>
                  <p className="kicker">{appText("text_5f308508b45b")}</p>
                  <h2 className="form-section-title">{appText("text_f34d137aba64")}</h2>
                  <p className="muted">{appText("text_6a499a471f04")}</p>
                </div>
              </div>

              <div className={styles.heroBody}>
                <div className={styles.heroWeightRow}>
                  <p className={`${styles.heroWeight} ${latestEntry ? "" : styles.heroWeightEmpty}`.trim()}>
                    {latestEntry ? latestEntry.weight_kg.toFixed(1) : appText("text_de687550b8fa")}
                  </p>
                  {latestEntry ? <p className={styles.heroUnit}>{appText("text_88ed32099fc7")}</p> : null}
                </div>

                <div className={styles.heroMetaGrid}>
                  <div className={styles.heroMetaCard}>
                    <p className={styles.heroMetaLabel}>{appText("text_ffe191a34207")}</p>
                    <p className={styles.heroMetaValue}>{formatBodyweightDate(latestEntry?.date ?? null)}</p>
                  </div>
                  <div className={styles.heroMetaCard}>
                    <p className={styles.heroMetaLabel}>{appText("text_978354db0c00")}</p>
                    <p className={styles.heroMetaValue}>{formatWeight(workspace.shared_camp_context.target_weight_kg ?? null)}</p>
                  </div>
                  <div className={styles.heroMetaCard}>
                    <p className={styles.heroMetaLabel}>{appText("text_73b4c9a69e84")}</p>
                    <p className={styles.heroMetaValue}>{formatWeightSource(workspace.shared_camp_context.current_weight_source)}</p>
                  </div>
                </div>
              </div>
            </section>

            <section className={styles.kpiRail}>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>{appText("text_c16431b1087a")}</p>
                <p className={styles.kpiValue}>{formatBmiValue(bmi)}</p>
                <p className={styles.kpiHelper}>
                  {bmi == null ? appText("text_8f392eb2b725") : appText("text_09c090f615e6")}
                </p>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>{appText("text_f7da9e525d6f")}</p>
                <p className={styles.kpiValue}>{formatWeight(sevenDayAverage)}</p>
                <p className={styles.kpiHelper}>{appText("text_46171ff3f475")}</p>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>{appText("text_066bc4277daf")}</p>
                <p className={styles.kpiValue}>{formatTargetGapLabel(targetGap)}</p>
                <p className={styles.kpiHelper}>
                  {targetGap == null ? appText("text_d13cf3c26022") : appText("text_625ad0b0cb4f")}
                </p>
              </article>
              <article className={styles.kpiCard}>
                <p className={styles.kpiLabel}>{appText("text_033f7216c0f4")}</p>
                <p className={styles.kpiValue}>{formatWeightDelta(recentChange)}</p>
                <p className={styles.kpiHelper}>
                  {recentChange == null
                    ? appText("text_a92d9dc68ba5")
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

            <section className={styles.quickAddShell} id="bodyweight-quick-add">
              <div className={styles.moduleHeader}>
                <div className={styles.moduleHeaderCopy}>
                  <p className="kicker">{appText("text_ee562d59348d")}</p>
                  <h2 className="form-section-title">{appText("text_18ae2df899f9")}</h2>
                  <p className="muted">{appText("text_32a398c4635b")}</p>
                </div>
              </div>

              <div className={styles.quickAddGrid}>
                <div className={`field ${styles.quickWeightField}`}>
                  <label>{appText("text_b48ca1a31a0f")}</label>
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
                    <label>{appText("text_99c40ab40592")}</label>
                    <input
                      type="date"
                      value={quickAdd.date}
                      onChange={(event) => setQuickAdd((current) => ({ ...current, date: event.target.value }))}
                    />
                  </div>
                  <div className="field">
                    <label>{appText("text_33b93476cf59")}</label>
                    <input
                      type="time"
                      value={quickAdd.time}
                      onChange={(event) => setQuickAdd((current) => ({ ...current, time: event.target.value }))}
                    />
                  </div>
                  <div className="field">
                    <label>{appText("text_eafd37f3611b")}</label>
                    <div className={styles.stateRail} aria-label={appText("text_400607abaacd")}>
                      {FASTED_OPTIONS.map((option) => (
                        <button
                          key={option.value}
                          type="button"
                          aria-pressed={quickAdd.is_fasted === option.value}
                          className={`${styles.stateButton} ${quickAdd.is_fasted === option.value ? styles.stateButtonActive : ""}`.trim()}
                          onClick={() => setQuickAdd((current) => ({ ...current, is_fasted: option.value }))}
                        >
                          {translateUiText(appText, option.label)}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className={`field ${styles.quickNotes}`}>
                    <label>{appText("text_8a7525b1492f")}</label>
                    <textarea
                      rows={3}
                      value={quickAdd.notes}
                      onChange={(event) => setQuickAdd((current) => ({ ...current, notes: event.target.value }))}
                    />
                  </div>
                </div>
              </div>

              <div className={styles.quickFooter}>
                <p className="muted">{appText("text_d3adbcf991be")}</p>
                <button type="button" className="cta" onClick={handleQuickAddSave} disabled={isPending}>
                  {isPending ? appText("text_dc85af8f2b1d") : appText("text_e5e18267c198")}
                </button>
              </div>
            </section>

            <section className={styles.historyShell}>
              <div className={styles.historyHeaderBar}>
                <div className={styles.moduleHeaderCopy}>
                  <p className="kicker">{appText("text_0e7696009337")}</p>
                  <h2 className="form-section-title">{appText("text_942daf79cc86")}</h2>
                  <p className="muted">{appText("text_13e3203941b9")}</p>
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
                            <p className={styles.historyWeight}>{entry.weight_kg.toFixed(1)} {appText("text_131ed734290d")}</p>
                            <div className={styles.historyMetaRow}>
                              <span className={styles.historyMetaTag}>{formatBodyweightTime(entry.time)}</span>
                              <span className={styles.historyMetaTag}>{formatFastedState(entry.is_fasted)}</span>
                              <span className={styles.historyMetaTag}>
                                {latestEntry && latestEntry.date === entry.date && latestEntry.time === entry.time && latestEntry.weight_kg === entry.weight_kg
                                  ? appText("text_8730d3c2022a")
                                  : previousEntry && previousEntry.date === entry.date && previousEntry.time === entry.time && previousEntry.weight_kg === entry.weight_kg
                                    ? appText("text_a57b08a480b8")
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
                              {appText("text_464c4ffd019e")}</button>
                            <button
                              type="button"
                              className="ghost-button danger-button"
                              onClick={() => handleDelete(entry.sourceIndex)}
                              disabled={isPending}
                            >
                              {appText("text_e2d0a54968ea")}</button>
                          </div>
                        </div>

                        {entry.notes ? <p className={styles.historyNotes}>{entry.notes}</p> : null}

                        {isEditing ? (
                          <div className={styles.historyEditor}>
                            <div className={styles.historyEditorGrid}>
                              <div className="field">
                                <label>{appText("text_99c40ab40592")}</label>
                                <input
                                  type="date"
                                  value={editingDraft.date}
                                  onChange={(event) =>
                                    setEditingDraft((current) => current ? { ...current, date: event.target.value } : current)
                                  }
                                />
                              </div>
                              <div className="field">
                                <label>{appText("text_b48ca1a31a0f")}</label>
                                <input
                                  type="number"
                                  step="0.1"
                                  inputMode="decimal"
                                  value={editingDraft.weight_kg}
                                  onChange={(event) =>
                                    setEditingDraft((current) => current ? { ...current, weight_kg: event.target.value } : current)
                                  }
                                />
                              </div>
                              <div className="field">
                                <label>{appText("text_33b93476cf59")}</label>
                                <input
                                  type="time"
                                  value={editingDraft.time}
                                  onChange={(event) =>
                                    setEditingDraft((current) => current ? { ...current, time: event.target.value } : current)
                                  }
                                />
                              </div>
                              <div className="field">
                                <label>{appText("text_eafd37f3611b")}</label>
                                <div className={styles.stateRail} aria-label={appText("text_a61cc80caf68")}>
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
                                      {translateUiText(appText, option.label)}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            </div>

                            <div className="field">
                              <label>{appText("text_8a7525b1492f")}</label>
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
                                {isPending ? appText("text_dc85af8f2b1d") : appText("text_dd0ae7a5cbcf")}
                              </button>
                              <button type="button" className="ghost-button" onClick={cancelEditing} disabled={isPending}>
                                {appText("text_19766ed6ccb2")}</button>
                            </div>
                          </div>
                        ) : null}
                      </article>
                    );
                  })}
                </div>
              ) : (
                <EmptyState
                  eyebrow={appText("text_0e2135ac0a2f")}
                  title={appText("text_eaf521638895")}
                  description={appText("text_013ed6df79f2")}
                  example={appText("text_c2553fbc21b1")}
                  primaryAction={{ label: "Log first weigh-in", href: "#bodyweight-quick-add" }}
                />
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
