import { setDraftsForFields } from "../exercise-log";
import { readSets, type SetDraft } from "../set-entries";
import { completeSet, currentItem, endSession, finishItem, finishItemAsPlanned, type TimerState, type TimerStep } from "./engine";

export function timerSetDrafts(state: TimerState, itemId = currentItem(state)?.id): SetDraft[] | null {
  const index = state.items.findIndex(item => item.id === itemId);
  const item = state.items[index];
  if (item?.kind !== "sets" || !item.setFields) return null;
  const current = index === state.index ? state.unit : 1;
  if (current > 50 || (item.sets?.max ?? 0) > 50) return null;
  const count = Math.min(50, Math.max(item.sets?.max ?? 1, current, state.completed[index] ?? 0));
  const previous = state.setDrafts?.[item.id] ?? [];
  const defaults = setDraftsForFields(item.setFields, {}, count);
  const effort = item.setFields.find(field => field.key === "effort")?.prescribed;
  return Array.from({ length: Math.max(count, previous.length) }, (_, at) => previous[at] ?? {
    ...defaults[at], ...(effort && effort[0] === effort[1] ? { rpe: String(effort[0]) } : {}),
  });
}

/** Set done starts rest immediately. Reporting measurements never blocks work. */
export function completeSetWithResults(state: TimerState, now: number): TimerStep {
  const item = currentItem(state);
  const rows = timerSetDrafts(state);
  if (!rows || item?.kind !== "sets" || state.phase !== "work" || state.pausedAt !== null) return completeSet(state, now);
  return completeSet({ ...state, setDrafts: { ...state.setDrafts, [item.id]: rows },
    confirmedSetLogs: state.confirmedSetLogs ?? {}, pendingSetLog: { itemId: item.id, set: state.unit } }, now);
}

export function confirmSetLog(state: TimerState, itemId: string, set: number): TimerState {
  const item = state.items.find(item => item.id === itemId);
  const rows = timerSetDrafts(state, itemId);
  const index = state.items.findIndex(item => item.id === itemId);
  if (item?.kind !== "sets" || !item.setFields || !rows || set < 1 || set > (state.completed[index] ?? 0)) return state;
  const unit = item.setFields.find(field => field.key === "load")?.apiUnit ?? "kg";
  if (readSets([rows[set - 1]], unit).invalid.length) return state;
  const confirmed = state.confirmedSetLogs?.[itemId] ?? [];
  return { ...state, setDrafts: { ...state.setDrafts, [itemId]: rows }, confirmedSetLogs: {
    ...state.confirmedSetLogs, [itemId]: [...new Set([...confirmed, set])],
  } };
}

export function unconfirmedSets(state: TimerState): { itemId: string; set: number }[] {
  if (state.confirmedSetLogs === undefined) return []; // Runs saved before rest logging.
  return state.items.flatMap((item, index) => item.kind !== "sets" || !item.setFields ? [] :
    Array.from({ length: state.completed[index] ?? 0 }, (_, at) => at + 1)
      .filter(set => !state.confirmedSetLogs?.[item.id]?.includes(set)).map(set => ({ itemId: item.id, set })));
}

export function confirmAllSetLogs(state: TimerState): TimerState {
  let next = state;
  for (const target of unconfirmedSets(state)) next = confirmSetLog(next, target.itemId, target.set);
  return next;
}

// Navigation never waits on a logging form. Unconfirmed measurements remain
// drafts and can be reviewed after training, while the countdown keeps running.
export const finishItemWithResults = (state: TimerState, now: number): TimerStep => finishItem(state, now);
export const finishItemAsPlannedWithResults = (state: TimerState, now: number): TimerStep => finishItemAsPlanned(state, now);
export const endSessionWithResults = (state: TimerState, now: number): TimerState => endSession(state, now);
