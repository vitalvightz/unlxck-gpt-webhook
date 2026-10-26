/** Small line icons for History records. Decorative unless a label is given. */

export type RecordStatus = "done" | "partial" | "missed" | "unknown";

const STATUS_BY_OUTCOME: Record<string, RecordStatus> = {
  as_prescribed: "done", done_as_shown: "done", modified: "partial", changed: "partial", skipped: "missed", stopped: "missed",
};

export function recordStatus(status: string | null | undefined, manual = false): RecordStatus {
  return manual ? "done" : STATUS_BY_OUTCOME[status ?? ""] ?? "unknown";
}

/** Shape carries the meaning as well as colour: check, half ring, cross, empty ring. */
export function StatusIcon({ status }: { status: RecordStatus }) {
  return <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" data-status={status}>
    {status === "done" ? <><circle cx="8" cy="8" r="8" fill="currentColor" /><path d="M4.6 8.2l2.2 2.2 4.6-4.8" fill="none" stroke="var(--bg-panel)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></>
      : status === "partial" ? <><circle cx="8" cy="8" r="6.6" fill="none" stroke="currentColor" strokeWidth="1.6" /><path d="M8 1.4a6.6 6.6 0 0 1 0 13.2z" fill="currentColor" /></>
      : status === "missed" ? <><circle cx="8" cy="8" r="6.6" fill="none" stroke="currentColor" strokeWidth="1.6" /><path d="M5.6 5.6l4.8 4.8M10.4 5.6l-4.8 4.8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></>
      : <circle cx="8" cy="8" r="6.6" fill="none" stroke="currentColor" strokeWidth="1.6" />}
  </svg>;
}

const PATHS = {
  source: <><circle cx="10" cy="10" r="7" /><circle cx="10" cy="10" r="2.2" /></>,
  effort: <path d="M4 15v-3M8 15V9M12 15V6M16 15V3" />,
  time: <><circle cx="10" cy="11" r="6.5" /><path d="M10 7.5V11l2.4 1.6M8 2.5h4" /></>,
  pain: <path d="M11 2.5L5 11h4.5L8.5 17.5 15 8.5h-4.5z" />,
};

export function TileIcon({ name }: { name: keyof typeof PATHS }) {
  return <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{PATHS[name]}</svg>;
}
