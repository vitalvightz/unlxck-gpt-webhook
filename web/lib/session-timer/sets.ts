import { setDraftsForFields } from "../exercise-log";
import { readSets, type SetDraft } from "../set-entries";
import { completeSet, currentItem, endSession, finishItem, finishItemAsPlanned, type TimerState, type TimerStep } from "./engine";

export function timerSetDrafts(state: TimerState): SetDraft[] | null {
  const item = currentItem(state);
  if (item?.kind !== "sets" || !item.setFields) return null;
  if (state.unit > 50 || (item.sets?.max ?? 0) > 50) return null;
  const count = Math.min(50, Math.max(item.sets?.max ?? 1, state.unit, state.completed[state.index] ?? 0));
  const previous = state.setDrafts?.[item.id] ?? [];
  const defaults = setDraftsForFields(item.setFields, {}, count);
  // Retain completed sets when the athlete lowers a target mid-workout.
  return Array.from({ length: Math.max(count, previous.length) }, (_, index) => previous[index] ?? defaults[index]);
}

/** The existing Set done action confirms measurements and starts rest once. */
export function completeSetWithResults(state: TimerState, now: number): TimerStep {
  const item = currentItem(state);
  const rows = timerSetDrafts(state);
  if (!rows || item?.kind !== "sets" || !item.setFields || state.phase !== "work") return completeSet(state, now);
  const unit = item.setFields.find(field => field.key === "load")?.apiUnit ?? "kg";
  if (readSets(rows.slice(0, state.unit), unit).invalid.length) return { state, events: [] };
  return completeSet({ ...state, setDrafts: { ...state.setDrafts, [item.id]: rows } }, now);
}

function invalidRecordedSets(state: TimerState, allCurrent = false): boolean {
  return state.items.some((item, index) => {
    if (item.kind !== "sets" || !item.setFields) return false;
    const rows = state.setDrafts?.[item.id];
    if (!rows) return false;
    const confirmed = allCurrent && index === state.index ? rows.length : state.completed[index] ?? 0;
    if (!confirmed) return false;
    const unit = item.setFields.find(field => field.key === "load")?.apiUnit ?? "kg";
    return readSets(rows.slice(0, confirmed), unit).invalid.length > 0;
  });
}

export function finishItemWithResults(state: TimerState, now: number): TimerStep {
  return invalidRecordedSets(state) ? { state, events: [] } : finishItem(state, now);
}

export function finishItemAsPlannedWithResults(state: TimerState, now: number): TimerStep {
  return invalidRecordedSets(state, true) ? { state, events: [] } : finishItemAsPlanned(state, now);
}

export function endSessionWithResults(state: TimerState, now: number): TimerState {
  return invalidRecordedSets(state) ? state : endSession(state, now);
}
