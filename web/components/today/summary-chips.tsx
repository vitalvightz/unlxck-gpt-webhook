import type { SummaryChip } from "@/lib/session-summary";

const CHIP_ICON_PATHS: Record<SummaryChip["icon"], string> = {
  clock: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 7.5V12l3 2",
  // Rising bars: how hard the day loads the body.
  load: "M6 19v-4M12 19V10M18 19V5",
  // A dumbbell: the number of exercises.
  exercises: "M3 12h18M6 8v8M9 6v12M15 6v12M18 8v8",
};

/** A training day's chips (time, load, exercises): Today's card and Home's Up Next. */
export function SummaryChipList({ chips }: { chips: SummaryChip[] }) {
  return (
    <ul className="today-session-chips" aria-label="Session summary">
      {chips.map((chip) => (
        <li key={chip.label}>
          <svg className="today-tool-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d={CHIP_ICON_PATHS[chip.icon]} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>
            {chip.estimate ? <><span aria-hidden="true">~</span><span className="sr-only">About </span></> : null}
            {chip.label}
          </span>
        </li>
      ))}
    </ul>
  );
}
