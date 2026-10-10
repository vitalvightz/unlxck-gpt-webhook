/** Shared exercise-type icons for Today, Plan and library discovery. */
export type ExerciseGlyphName =
  | "strength" | "power" | "conditioning" | "mobility" | "recovery" | "rehab"
  | "skill" | "visualisation" | "tactical" | "breathing";

const PATHS: Record<ExerciseGlyphName, string> = {
  strength: "M3 12h18M6 8v8M9 6v12M15 6v12M18 8v8",
  power: "M13 2 4 14h7l-1 8 9-12h-7z",
  conditioning: "M3 12h4l2-5 4 10 2-5h6",
  mobility: "M20 12a8 8 0 1 1-2.3-5.7M20 4v4h-4",
  recovery: "M5 19c0-8 6-14 14-14 0 8-6 14-14 14zM5 19l7-7",
  rehab: "M12 3l7 3v5c0 4.5-3 8.2-7 10-4-1.8-7-5.5-7-10V6zM12 9v6M9 12h6",
  skill: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12h.01",
  visualisation: "M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 1V5a3 3 0 0 0-3-1zM15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-6 1",
  tactical: "M3 5h18v12H3zM8 21h8M12 17v4M10 8.5v5l4-2.5z",
  breathing: "M3 9h11a3 3 0 1 0-3-3M3 15h15a3 3 0 1 1-3 3M3 12h7",
};

export function ExerciseGlyphIcon({ name }: { name: ExerciseGlyphName }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={PATHS[name]} fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
