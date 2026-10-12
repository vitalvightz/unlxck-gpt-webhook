import type { ExerciseChangeDose, StructuredBlock } from "@/lib/types";

export type DoseDraft = Partial<Record<"sets" | "reps" | "rounds" | "work_seconds" | "duration_seconds" | "rest_seconds" | "distance" | "rpe", number | null>> & {
  mode: ExerciseChangeDose["mode"];
  distance_unit?: "m" | "km" | "mi" | "yd";
  prescription?: string;
  load_or_intensity?: string;
  tempo?: string;
  per_side?: boolean;
};

function seconds(value: StructuredBlock["duration"]): number | null {
  if (!value || typeof value.value !== "number") return null;
  return Math.round(value.value * (/^min/i.test(value.unit ?? "") ? 60 : 1));
}

export function doseFromBlock(block: StructuredBlock): DoseDraft {
  const saved = block.athlete_dose as DoseDraft | null;
  if (saved?.mode) return { ...saved };
  const mode = block.rounds && block.work ? "intervals" : block.distance ? "distance"
    : block.duration ? "duration" : block.sets && block.reps ? "reps" : "text";
  return {
    mode, sets: block.sets ?? null, reps: typeof block.reps === "number" ? block.reps : null,
    rounds: block.rounds ?? null, work_seconds: seconds(block.work), duration_seconds: seconds(block.duration),
    rest_seconds: seconds(block.rest), distance: block.distance?.value ?? null,
    distance_unit: (block.distance?.unit ?? "m") as DoseDraft["distance_unit"],
    rpe: block.effort?.method === "RPE" && typeof block.effort.value === "number" ? block.effort.value : null,
    load_or_intensity: block.load?.display || block.intensity || "", tempo: "",
    prescription: block.prescription_text || "",
  };
}

export function validDose(dose: DoseDraft): boolean {
  const integer = (value: number | null | undefined, min: number, max: number) =>
    typeof value === "number" && Number.isInteger(value) && value >= min && value <= max;
  const optionalInteger = (value: number | null | undefined, min: number, max: number) =>
    value == null || integer(value, min, max);
  if (!optionalInteger(dose.sets, 1, 100) || !optionalInteger(dose.rest_seconds, 0, 3600)
    || (dose.rpe != null && (!Number.isFinite(dose.rpe) || dose.rpe < 1 || dose.rpe > 10))) return false;
  if (dose.mode === "reps") return integer(dose.sets, 1, 100) && integer(dose.reps, 1, 1000);
  if (dose.mode === "intervals") return integer(dose.rounds, 1, 100) && integer(dose.work_seconds, 1, 36000) && integer(dose.rest_seconds, 0, 3600);
  if (dose.mode === "duration") return integer(dose.duration_seconds, 1, 36000);
  if (dose.mode === "distance") return typeof dose.distance === "number" && dose.distance > 0 && dose.distance <= 100000 && Boolean(dose.distance_unit);
  return Boolean(dose.prescription?.trim());
}

export function finishedDose(dose: DoseDraft): ExerciseChangeDose {
  const common = { rest_seconds: dose.rest_seconds ?? null, load_or_intensity: dose.load_or_intensity || null,
    rpe: dose.rpe ?? null, ...(dose.mode !== "distance" ? { tempo: dose.tempo || null } : {}), per_side: dose.per_side ?? null };
  switch (dose.mode) {
    case "reps": return { ...common, mode: "reps", sets: dose.sets!, reps: dose.reps! };
    case "duration": return { ...common, mode: "duration", sets: dose.sets ?? null, duration_seconds: dose.duration_seconds! };
    case "intervals": return { ...common, mode: "intervals", rounds: dose.rounds!, work_seconds: dose.work_seconds!, rest_seconds: dose.rest_seconds! };
    case "distance": return { ...common, mode: "distance", sets: dose.sets ?? null, distance: dose.distance!, distance_unit: dose.distance_unit! };
    case "text": return { ...common, mode: "text", prescription: dose.prescription!.trim() };
  }
}
