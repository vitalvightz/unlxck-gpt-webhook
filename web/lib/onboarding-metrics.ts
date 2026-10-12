import type { AdminTimeToFirstPlanSummary } from "@/lib/types";

/** "45s", "4m", "1h 20m", "2d 3h": compact enough for a summary tile. */
export function formatWaitDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
    return "-";
  }
  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    const rest = minutes % 60;
    return rest ? `${hours}h ${rest}m` : `${hours}h`;
  }
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return restHours ? `${days}d ${restHours}h` : `${days}d`;
}

/** Supporting line under the median: how many signups reached a usable plan. */
export function describeFirstPlanConversion(summary: AdminTimeToFirstPlanSummary): string {
  const { signups, with_usable_plan: activated, window_days: days, p75_seconds: p75 } = summary;
  if (signups === 0) {
    return `No signups in the last ${days} days.`;
  }
  const base = `${activated} of ${signups} signup${signups === 1 ? "" : "s"} have a plan (${days}d).`;
  return p75 === null || p75 === undefined ? base : `${base} p75 ${formatWaitDuration(p75)}.`;
}
