"use client";

import { useMemo, useState } from "react";
import { GUIDED_INJURY_AREA_MAX, GUIDED_INJURY_NOTES_MAX } from "@/lib/input-limits";
import { hasGuidedInjuryReviewRisk, type GuidedInjuryState } from "@/lib/guided-injury";
import {
  GUIDED_INJURY_SEVERITY_OPTIONS,
  type IntakeOption,
} from "@/lib/intake-options";

// ── Injury-type option groups ────────────────────────────────────────

type InjuryTypeOption = {
  label: string;
  value: string;
  surface_type?: string;
};

type InjuryTypeGroup = {
  heading: string;
  options: InjuryTypeOption[];
};
type InjuryFamily = "pain_movement" | "structural" | "head_nerve_breathing" | "surface" | "not_sure";
type InjuryFamilyOption = { family: InjuryFamily; label: string; helper: string };

const INJURY_TYPE_GROUPS: InjuryTypeGroup[] = [
  {
    heading: "Common",
    options: [
      { label: "Pain / soreness", value: "pain" },
      { label: "Tightness", value: "tightness" },
      { label: "Sprain", value: "sprain" },
      { label: "Strain / pulled muscle", value: "strain" },
      { label: "Swelling", value: "swelling" },
      { label: "Instability / giving way", value: "instability" },
      { label: "Not sure", value: "unspecified" },
    ],
  },
  {
    heading: "Structural / serious",
    options: [
      { label: "Fracture / broken bone", value: "fracture" },
      { label: "Dislocation", value: "dislocation" },
      { label: "Tendon / ligament issue", value: "tendon_ligament" },
      { label: "Post-surgery / reconstruction", value: "post_surgery" },
    ],
  },
  {
    heading: "Head / nerve / breathing",
    options: [
      { label: "Head impact / concussion", value: "head_impact" },
      { label: "Numbness / tingling / weakness", value: "nerve_symptoms" },
      { label: "Chest or breathing pain", value: "chest_breathing" },
    ],
  },
  {
    heading: "Surface",
    options: [
      { label: "Cut / wound", value: "surface_injury", surface_type: "cut" },
      { label: "Laceration / deep cut", value: "surface_injury", surface_type: "laceration" },
      { label: "Graze / abrasion / mat burn", value: "surface_injury", surface_type: "abrasion" },
      { label: "Blister", value: "surface_injury", surface_type: "blister" },
      { label: "Bruise / contusion", value: "surface_injury", surface_type: "bruise" },
      { label: "Burn / skin irritation", value: "surface_injury", surface_type: "skin_irritation" },
    ],
  },
];

const INJURY_FAMILIES: InjuryFamilyOption[] = [
  { family: "pain_movement", label: "Muscle / tendon / joint pain", helper: "Soreness, tightness, strains. Used as fallback if description is unclear." },
  { family: "structural", label: "Bone or dislocation", helper: "Fracture, dislocation, ligament. Used as fallback if description is unclear." },
  { family: "head_nerve_breathing", label: "Head, nerve or breathing issue", helper: "Concussion, nerve, breathing. Used as fallback if description is unclear." },
  { family: "surface", label: "Skin injury", helper: "Cuts, blisters, bruises. Used as fallback if description is unclear." },
  { family: "not_sure", label: "Not sure", helper: "I do not know yet. Used as fallback if description is unclear." },
];

const FAMILY_TO_HEADING: Record<Exclude<InjuryFamily, "not_sure">, string> = {
  pain_movement: "Common",
  structural: "Structural / serious",
  head_nerve_breathing: "Head / nerve / breathing",
  surface: "Surface",
};

// ── Timeframe options ────────────────────────────────────────────────

const TIMEFRAME_OPTIONS: IntakeOption[] = [
  { label: "Today", value: "today" },
  { label: "This week", value: "this_week" },
  { label: "Last week", value: "last_week" },
  { label: "Last month", value: "last_month" },
  { label: "1–3 months ago", value: "one_to_three_months" },
  { label: "3+ months ago", value: "three_plus_months" },
  { label: "Old / cleared", value: "old_cleared" },
  { label: "Not sure", value: "not_sure" },
];

const CLEARED_OPTIONS: IntakeOption[] = [
  { label: "Yes", value: "yes" },
  { label: "No", value: "no" },
  { label: "Not sure", value: "not_sure" },
];

const YES_NO_UNSURE: IntakeOption[] = [
  { label: "Yes", value: "yes" },
  { label: "No", value: "no" },
  { label: "Not sure", value: "not_sure" },
];

const BLEEDING_STATUS_OPTIONS: IntakeOption[] = [
  { label: "None", value: "none" },
  { label: "A little", value: "a_little" },
  { label: "Won't stop", value: "wont_stop" },
];

const OPEN_WOUND_OPTIONS: IntakeOption[] = [
  { label: "No", value: "no" },
  { label: "Yes", value: "yes" },
  { label: "Not sure", value: "not_sure" },
];

const SENSITIVE_AREA_OPTIONS: IntakeOption[] = [
  { label: "No", value: "no" },
  { label: "Face", value: "face" },
  { label: "Eye", value: "eye" },
  { label: "Mouth", value: "mouth" },
];

const INFECTION_SIGNS_OPTIONS: IntakeOption[] = [
  { label: "Redness / heat", value: "redness_heat" },
  { label: "Pus", value: "pus" },
  { label: "Fever", value: "fever" },
  { label: "Spreading", value: "spreading" },
  { label: "None", value: "none" },
];

// ── Avoid chips per injury type ──────────────────────────────────────

const AVOID_CHIPS: Record<string, string[]> = {
  fracture: ["running", "sprinting", "jumping", "cutting", "contact_sparring", "heavy_loading", "deep_range", "not_sure"],
  dislocation: ["contact_sparring", "grappling", "overhead_work", "heavy_loading", "deep_range"],
  tendon_ligament: ["sprinting", "jumping", "cutting", "contact_sparring", "heavy_loading", "deep_range"],
  post_surgery: ["contact_sparring", "heavy_loading", "running", "jumping", "deep_range"],
  surface_abrasion: ["contact_sparring", "friction", "grappling"],
  surface_blister: ["running", "gripping", "contact_sparring", "footwear_friction"],
  surface_bruise: ["contact_sparring", "heavy_loading", "impact", "running"],
  surface_cut: ["contact_sparring", "grappling", "friction"],
  surface_laceration: ["contact_sparring", "grappling", "friction"],
  surface_skin_irritation: ["friction", "contact_sparring", "sweating_under_kit"],
};

const AVOID_CHIP_LABELS: Record<string, string> = {
  running: "Running",
  sprinting: "Sprinting",
  jumping: "Jumping",
  cutting: "Cutting",
  contact_sparring: "Contact / sparring",
  heavy_loading: "Heavy loading",
  deep_range: "Deep range",
  not_sure: "Not sure",
  grappling: "Grappling",
  overhead_work: "Overhead work",
  friction: "Friction",
  gripping: "Gripping",
  footwear_friction: "Footwear friction",
  impact: "Impact",
  sweating_under_kit: "Sweating under kit",
};

// ── Head-impact red-flag checklist ───────────────────────────────────

const HEAD_RED_FLAGS = [
  { label: "Loss of consciousness", value: "loss_of_consciousness" },
  { label: "Vomiting", value: "vomiting" },
  { label: "Severe headache", value: "severe_headache" },
  { label: "Memory loss", value: "memory_loss" },
  { label: "Blurred or double vision", value: "blurred_or_double_vision" },
  { label: "Confusion", value: "confusion" },
];

// ── Trend options ────────────────────────────────────────────────────

const INJURY_TREND_OPTIONS: IntakeOption[] = [
  { label: "Stable", value: "stable" },
  { label: "Improving", value: "improving" },
  { label: "Getting worse", value: "worsening" },
];

const TREND_ARROWS: Record<string, string> = {
  stable: "→",
  improving: "↗",
  worsening: "↘",
};

// ── Helpers ──────────────────────────────────────────────────────────

function getSelectedTypeOption(injury: GuidedInjuryState): InjuryTypeOption | null {
  for (const group of INJURY_TYPE_GROUPS) {
    for (const opt of group.options) {
      if (opt.value === injury.injury_type) {
        if (opt.value === "surface_injury") {
          if (opt.surface_type === injury.surface_type) return opt;
        } else {
          return opt;
        }
      }
    }
  }
  return null;
}

function getInjuryTypeLabel(injury: GuidedInjuryState): string {
  const opt = getSelectedTypeOption(injury);
  return opt?.label ?? injury.injury_type ?? "";
}

function getInjurySubtypeLabels(injury: GuidedInjuryState): string[] {
  const subtypes = injury.injury_subtypes ?? [];
  if (subtypes.length === 0) return [];

  const allOptions = INJURY_TYPE_GROUPS.flatMap((group) => group.options);
  return subtypes
    .map((subtype) => allOptions.find((option) => getSubtypeKey(option) === subtype)?.label ?? subtype)
    .filter(Boolean);
}

function getSubtypeKey(option: InjuryTypeOption): string {
  return option.surface_type ? `${option.value}:${option.surface_type}` : option.value;
}

function getFamilyForInjury(injury: GuidedInjuryState): InjuryFamily | "" {
  if (injury.injury_type === "surface_injury") return "surface";
  if (["pain", "tightness", "sprain", "strain", "swelling", "instability"].includes(injury.injury_type)) return "pain_movement";
  if (["fracture", "dislocation", "tendon_ligament", "post_surgery"].includes(injury.injury_type)) return "structural";
  if (["head_impact", "nerve_symptoms", "chest_breathing"].includes(injury.injury_type)) return "head_nerve_breathing";
  if (injury.injury_type === "unspecified") return "not_sure";
  return "";
}

function getOptionsForFamily(family: InjuryFamily): InjuryTypeOption[] {
  if (family === "not_sure") return [{ label: "Not sure", value: "unspecified" }];
  if (family === "pain_movement") {
    const common = INJURY_TYPE_GROUPS.find((item) => item.heading === "Common")?.options.filter((opt) => opt.value !== "unspecified") ?? [];
    return [...common, { label: "Tendon / ligament issue", value: "tendon_ligament" }, { label: "Not sure", value: "unspecified" }];
  }
  const heading = FAMILY_TO_HEADING[family];
  const group = INJURY_TYPE_GROUPS.find((item) => item.heading === heading);
  if (!group) return [];
  return group.options;
}

function isSafetyComplete(injury: GuidedInjuryState, family: InjuryFamily | ""): boolean {
  if (!injury.injury_type) return false;
  if (injury.injury_type === "unspecified") {
    if (family === "structural") {
      const hasStructuralBearWeight = Boolean(getSingleNotesFlag(injury.notes, "structural", "bear_weight"));
      const hasStructuralSwelling = Boolean(getSingleNotesFlag(injury.notes, "structural", "swelling"));
      const hasStructuralDeformity = Boolean(getSingleNotesFlag(injury.notes, "structural", "deformity"));
      return Boolean(
        injury.timeframe &&
        injury.cleared &&
        injury.impact_related &&
        hasStructuralBearWeight &&
        hasStructuralSwelling &&
        hasStructuralDeformity
      );
    }
    if (family === "head_nerve_breathing") return Boolean(parseNotesFlags(injury.notes, "red_flags").length > 0 && parseNotesFlags(injury.notes, "nerve_symptoms").length > 0 && parseNotesFlags(injury.notes, "chest_symptoms").length > 0 && injury.impact_related);
    if (family === "surface") return Boolean(injury.open_wound && injury.bleeding_status && injury.sensitive_area && injury.infection_signs.length > 0);
    return true;
  }
  if (injury.injury_type === "fracture") return Boolean(injury.timeframe && injury.cleared);
  if (injury.injury_type === "dislocation") return Boolean(getSingleNotesFlag(injury.notes, "dislocation", "relocated") && getSingleNotesFlag(injury.notes, "dislocation", "recurrent") && injury.cleared);
  if (["tendon_ligament", "post_surgery"].includes(injury.injury_type)) return Boolean(injury.timeframe && injury.cleared);
  if (injury.injury_type === "head_impact") return parseNotesFlags(injury.notes, "red_flags").length > 0;
  if (injury.injury_type === "nerve_symptoms") return Boolean(getSingleNotesFlag(injury.notes, "nerve_symptoms", "type") && injury.impact_related);
  if (injury.injury_type === "chest_breathing") return Boolean(parseNotesFlags(injury.notes, "chest_symptoms").length > 0 && injury.impact_related);
  if (injury.injury_type === "surface_injury") {
    if (["cut", "laceration"].includes(injury.surface_type)) return Boolean(injury.bleeding_status && injury.open_wound && injury.sensitive_area);
    if (["abrasion", "blister", "skin_irritation"].includes(injury.surface_type)) return Boolean(injury.open_wound);
    if (injury.surface_type === "bruise") return Boolean(injury.impact_related);
    return false;
  }
  return true;
}

function getAvoidChipsForInjury(injury: GuidedInjuryState): string[] {
  if (injury.injury_type === "surface_injury" && injury.surface_type) {
    return AVOID_CHIPS[`surface_${injury.surface_type}`] ?? [];
  }
  return AVOID_CHIPS[injury.injury_type] ?? [];
}

function toggleAvoidChip(current: string, chip: string): string {
  const parts = current.split(",").map((s) => s.trim()).filter(Boolean);
  if (parts.includes(chip)) {
    return parts.filter((p) => p !== chip).join(", ");
  }
  return [...parts, chip].join(", ");
}

function hasAvoidChip(current: string, chip: string): boolean {
  return current.split(",").map((s) => s.trim()).includes(chip);
}

function parseNotesFlags(notes: string, prefix: string): string[] {
  const match = notes.match(new RegExp(`\\[${prefix}:([^\\]]+)\\]`));
  if (!match?.[1]) return [];
  return match[1].split(",").map((s) => s.trim()).filter(Boolean);
}

function setNotesFlags(notes: string, prefix: string, flags: string[]): string {
  const cleaned = notes.replace(new RegExp(`\\s*\\[${prefix}:[^\\]]*\\]`), "").trim();
  if (!flags.length) return cleaned;
  return `${cleaned} [${prefix}:${flags.join(",")}]`.trim();
}

function toggleNotesFlag(notes: string, prefix: string, flag: string): string {
  const current = parseNotesFlags(notes, prefix);
  const next = current.includes(flag)
    ? current.filter((f) => f !== flag)
    : [...current, flag];
  return setNotesFlags(notes, prefix, next);
}

function toggleExclusiveNoneFlag(notes: string, prefix: string, currentFlags: string[], selectedFlag: string): string {
  if (selectedFlag === "none") {
    return setNotesFlags(notes, prefix, currentFlags.includes("none") ? [] : ["none"]);
  }
  const withoutNone = currentFlags.filter((flag) => flag !== "none");
  const next = withoutNone.includes(selectedFlag)
    ? withoutNone.filter((flag) => flag !== selectedFlag)
    : [...withoutNone, selectedFlag];
  return setNotesFlags(notes, prefix, next);
}


function setSingleNotesFlag(notes: string, prefix: string, group: string, value: string): string {
  const current = parseNotesFlags(notes, prefix).filter((flag) => !flag.startsWith(`${group}_`));
  if (!value) return setNotesFlags(notes, prefix, current);
  return setNotesFlags(notes, prefix, [...current, `${group}_${value}`]);
}

function getSingleNotesFlag(notes: string, prefix: string, group: string): string {
  const found = parseNotesFlags(notes, prefix).find((flag) => flag.startsWith(`${group}_`));
  return found ? found.slice(group.length + 1) : "";
}

function stripTaggedNotes(notes: string, prefixes: string[]): string {
  return prefixes
    .reduce((next, prefix) => next.replace(new RegExp(`\\s*\\[${prefix}:[^\\]]*\\]`, "g"), ""), notes)
    .trim();
}

// The notes field is overloaded: it holds the athlete's free-text extra detail
// plus structured safety flags such as "[red_flags:none]". These helpers keep
// the two apart so the visible "Extra detail" box only ever shows real prose.

const NOTE_TAG_PATTERN = /\s?\[[a-z_]+:[^\]]*\]/gi;

// Returns the athlete-typed prose with the structured flags removed. Internal
// spacing is preserved so the value can drive a controlled textarea faithfully.
function getNotesFreeText(notes: string): string {
  return notes.replace(NOTE_TAG_PATTERN, "");
}

// Rewrites the free-text portion while keeping any structured flags appended.
function setNotesFreeText(notes: string, freeText: string): string {
  const tags = notes.match(/\[[a-z_]+:[^\]]*\]/gi) ?? [];
  if (!tags.length) return freeText;
  if (!freeText.trim()) return tags.join(" ");
  return `${freeText} ${tags.join(" ")}`;
}

function clearTypeSpecificFields(onUpdate: <K extends keyof GuidedInjuryState>(key: K, value: GuidedInjuryState[K]) => void) {
  onUpdate("surface_type", "");
  onUpdate("timeframe", "");
  onUpdate("cleared", "");
  onUpdate("open_wound", "");
  onUpdate("bleeding_status", "");
  onUpdate("infection_signs", []);
  onUpdate("impact_related", "");
  onUpdate("sensitive_area", "");
  onUpdate("avoid", "");
}

// ── Build compact summary line ───────────────────────────────────────

export function buildCompactSummary(injury: GuidedInjuryState): string {
  const parts: string[] = [];
  if (injury.area) parts.push(injury.area);
  const typeLabel = getInjuryTypeLabel(injury);
  if (typeLabel) parts.push(typeLabel);
  if (injury.severity) parts.push(injury.severity.charAt(0).toUpperCase() + injury.severity.slice(1));
  if (injury.trend) parts.push(injury.trend.charAt(0).toUpperCase() + injury.trend.slice(1));
  if (injury.timeframe) {
    const tf = TIMEFRAME_OPTIONS.find((o) => o.value === injury.timeframe);
    if (tf) parts.push(tf.label);
  }
  if (injury.injury_type === "surface_injury" && injury.open_wound === "yes") {
    parts.push("Open wound");
  }
  return parts.join(" · ");
}

function truncateForHeader(value: string, max = 72): string {
  const text = value.trim().replace(/\s+/g, " ");
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

// ── Chip button component ────────────────────────────────────────────

function ChipButton({
  label,
  selected,
  onClick,
  variant,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
  variant?: "default" | "danger";
}) {
  const base = "gi-chip";
  const cls = [
    base,
    selected ? "gi-chip-selected" : "",
    variant === "danger" && selected ? "gi-chip-danger" : "",
  ].filter(Boolean).join(" ");

  return (
    <button
      type="button"
      className={cls}
      aria-pressed={selected}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

// ── Multi-select chip row ────────────────────────────────────────────

function ChipRow({
  label,
  options,
  selected,
  onToggle,
  variant,
}: {
  label: string;
  options: IntakeOption[];
  selected: string[];
  onToggle: (value: string) => void;
  variant?: "default" | "danger";
}) {
  return (
    <fieldset className="gi-chip-fieldset" aria-label={label}>
      <div className="gi-chip-row" role="group">
        {options.map((opt) => (
          <ChipButton
            key={opt.value}
            label={opt.label}
            selected={selected.includes(opt.value)}
            onClick={() => onToggle(opt.value)}
            variant={variant}
          />
        ))}
      </div>
    </fieldset>
  );
}

// ── Single-select chip row ───────────────────────────────────────────

function SingleChipRow({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: IntakeOption[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <fieldset className="gi-chip-fieldset" aria-label={label}>
      <div className="gi-chip-row" role="radiogroup" aria-label={label}>
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={value === opt.value}
            className={`gi-chip ${value === opt.value ? "gi-chip-selected" : ""}`}
            onClick={() => onChange(value === opt.value ? "" : opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

// ── Progressive follow-up questions ──────────────────────────────────

function FollowUpQuestions({
  injury,
  family,
  onUpdate,
}: {
  injury: GuidedInjuryState;
  family: InjuryFamily | "";
  onUpdate: <K extends keyof GuidedInjuryState>(key: K, value: GuidedInjuryState[K]) => void;
}) {
  const { injury_type, surface_type } = injury;
  if (injury_type === "unspecified" && family === "structural") {
    return <div className="gi-followup">
      <div className="gi-field"><label className="gi-label">When did it happen?</label><SingleChipRow label="Timeframe" options={TIMEFRAME_OPTIONS} value={injury.timeframe} onChange={(v) => onUpdate("timeframe", v)} /></div>
      <div className="gi-field"><label className="gi-label">Have you been medically cleared?</label><SingleChipRow label="Cleared" options={CLEARED_OPTIONS} value={injury.cleared} onChange={(v) => onUpdate("cleared", v)} /></div>
      <div className="gi-field"><label className="gi-label">Can you bear weight?</label><SingleChipRow label="Bear weight" options={YES_NO_UNSURE} value={getSingleNotesFlag(injury.notes, "structural", "bear_weight")} onChange={(v) => onUpdate("notes", setSingleNotesFlag(injury.notes, "structural", "bear_weight", v))} /></div>
      <div className="gi-field"><label className="gi-label">Is there rapid swelling?</label><SingleChipRow label="Swelling" options={YES_NO_UNSURE} value={getSingleNotesFlag(injury.notes, "structural", "swelling")} onChange={(v) => onUpdate("notes", setSingleNotesFlag(injury.notes, "structural", "swelling", v))} /></div>
      <div className="gi-field"><label className="gi-label">Is there deformity?</label><SingleChipRow label="Deformity" options={YES_NO_UNSURE} value={getSingleNotesFlag(injury.notes, "structural", "deformity")} onChange={(v) => onUpdate("notes", setSingleNotesFlag(injury.notes, "structural", "deformity", v))} /></div>
      <div className="gi-field"><label className="gi-label">Does it feel unstable or giving way?</label><SingleChipRow label="Unstable" options={YES_NO_UNSURE} value={injury.impact_related} onChange={(v) => onUpdate("impact_related", v)} /></div>
    </div>;
  }
  if (injury_type === "unspecified" && family === "head_nerve_breathing") {
    const headFlags = parseNotesFlags(injury.notes, "red_flags");
    const nerveFlags = parseNotesFlags(injury.notes, "nerve_symptoms");
    const chestFlags = parseNotesFlags(injury.notes, "chest_symptoms");
    return <div className="gi-followup">
      <div className="gi-field"><label className="gi-label">Any head-impact red flags?</label><div className="gi-chip-row" role="group">{[...HEAD_RED_FLAGS, { label: "None", value: "none" }].map((flag) => <ChipButton key={flag.value} label={flag.label} selected={headFlags.includes(flag.value)} onClick={() => onUpdate("notes", toggleExclusiveNoneFlag(injury.notes, "red_flags", headFlags, flag.value))} variant="danger" />)}</div></div>
      <div className="gi-field"><label className="gi-label">Any numbness, tingling, or weakness?</label><div className="gi-chip-row" role="group">{[{ label: "Numbness", value: "type_numbness" }, { label: "Tingling", value: "type_tingling" }, { label: "Weakness", value: "type_weakness" }, { label: "Mixed", value: "type_mixed" }, { label: "None", value: "none" }].map((flag) => <ChipButton key={flag.value} label={flag.label} selected={nerveFlags.includes(flag.value)} onClick={() => onUpdate("notes", toggleExclusiveNoneFlag(injury.notes, "nerve_symptoms", nerveFlags, flag.value))} />)}</div></div>
      <div className="gi-field"><label className="gi-label">Any chest or breathing symptoms?</label><div className="gi-chip-row" role="group">{[{ label: "Pain when breathing", value: "breathing_pain" }, { label: "Shortness of breath", value: "shortness_of_breath" }, { label: "Chest pain", value: "chest_pain" }, { label: "Coughing blood", value: "coughing_blood" }, { label: "None", value: "none" }].map((flag) => <ChipButton key={flag.value} label={flag.label} selected={chestFlags.includes(flag.value)} onClick={() => onUpdate("notes", toggleExclusiveNoneFlag(injury.notes, "chest_symptoms", chestFlags, flag.value))} variant="danger" />)}</div></div>
      <div className="gi-field"><label className="gi-label">Did it follow impact/contact?</label><SingleChipRow label="Impact related" options={YES_NO_UNSURE} value={injury.impact_related} onChange={(v) => onUpdate("impact_related", v)} /></div>
    </div>;
  }

  if (injury_type === "unspecified" && family === "surface") return <SurfaceFollowUp injury={injury} onUpdate={onUpdate} />;

  if (injury_type === "fracture") {
    return (
      <div className="gi-followup">
        <div className="gi-field">
          <label className="gi-label">When did it happen?</label>
          <SingleChipRow label="Timeframe" options={TIMEFRAME_OPTIONS} value={injury.timeframe} onChange={(v) => onUpdate("timeframe", v)} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Have you been medically cleared?</label>
          <SingleChipRow label="Cleared" options={CLEARED_OPTIONS} value={injury.cleared} onChange={(v) => onUpdate("cleared", v)} />
        </div>
        <AvoidChips injury={injury} onUpdate={onUpdate} />
      </div>
    );
  }

  if (injury_type === "dislocation") {
    return (
      <div className="gi-followup">
        <div className="gi-field">
          <label className="gi-label">Did it go back into place?</label>
          <SingleChipRow label="Relocated" options={YES_NO_UNSURE} value={getSingleNotesFlag(injury.notes, "dislocation", "relocated")} onChange={(v) => onUpdate("notes", setSingleNotesFlag(injury.notes, "dislocation", "relocated", v))} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Has this happened before?</label>
          <SingleChipRow label="Recurrent" options={YES_NO_UNSURE} value={getSingleNotesFlag(injury.notes, "dislocation", "recurrent")} onChange={(v) => onUpdate("notes", setSingleNotesFlag(injury.notes, "dislocation", "recurrent", v))} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Have you been medically cleared?</label>
          <SingleChipRow label="Cleared" options={CLEARED_OPTIONS} value={injury.cleared} onChange={(v) => onUpdate("cleared", v)} />
        </div>
        <AvoidChips injury={injury} onUpdate={onUpdate} />
      </div>
    );
  }

  if (injury_type === "tendon_ligament") {
    return (
      <div className="gi-followup">
        <div className="gi-field">
          <label className="gi-label">When did it happen?</label>
          <SingleChipRow label="Timeframe" options={TIMEFRAME_OPTIONS} value={injury.timeframe} onChange={(v) => onUpdate("timeframe", v)} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Have you been medically cleared?</label>
          <SingleChipRow label="Cleared" options={CLEARED_OPTIONS} value={injury.cleared} onChange={(v) => onUpdate("cleared", v)} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Does it feel unstable or giving way?</label>
          <SingleChipRow label="Unstable" options={YES_NO_UNSURE} value={injury.impact_related} onChange={(v) => onUpdate("impact_related", v)} />
        </div>
        <AvoidChips injury={injury} onUpdate={onUpdate} />
      </div>
    );
  }

  if (injury_type === "post_surgery") {
    return (
      <div className="gi-followup">
        <div className="gi-field">
          <label className="gi-label">When was surgery?</label>
          <SingleChipRow label="Timeframe" options={TIMEFRAME_OPTIONS} value={injury.timeframe} onChange={(v) => onUpdate("timeframe", v)} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Have you been medically cleared?</label>
          <SingleChipRow label="Cleared" options={CLEARED_OPTIONS} value={injury.cleared} onChange={(v) => onUpdate("cleared", v)} />
        </div>
        <AvoidChips injury={injury} onUpdate={onUpdate} />
      </div>
    );
  }

  if (injury_type === "head_impact") {
    const flags = parseNotesFlags(injury.notes, "red_flags");
    const hasNone = flags.includes("none");
    return (
      <div className="gi-followup">
        <div className="gi-field">
          <label className="gi-label gi-label-danger">Red-flag checklist</label>
          <div className="gi-chip-row" role="group" aria-label="Red-flag symptoms">
            {HEAD_RED_FLAGS.map((flag) => (
              <ChipButton
                key={flag.value}
                label={flag.label}
                selected={flags.includes(flag.value)}
                onClick={() => onUpdate("notes", toggleNotesFlag(setNotesFlags(injury.notes, "red_flags", flags.filter((f) => f !== "none")), "red_flags", flag.value))}
                variant="danger"
              />
            ))}
            <ChipButton
              label="None of these"
              selected={hasNone}
              onClick={() => onUpdate("notes", setNotesFlags(injury.notes, "red_flags", hasNone ? [] : ["none"]))}
            />
          </div>
        </div>
        <p className="gi-warning gi-warning-red" role="alert">
          Head-impact symptoms may pause planning until review.
        </p>
      </div>
    );
  }

  if (injury_type === "nerve_symptoms") {
    return (
      <div className="gi-followup">
        <div className="gi-field">
          <label className="gi-label">What are you feeling?</label>
          <SingleChipRow
            label="Symptom type"
            options={[
              { label: "Numbness", value: "numbness" },
              { label: "Tingling", value: "tingling" },
              { label: "Weakness", value: "weakness" },
              { label: "Mixed", value: "mixed" },
            ]}
            value={getSingleNotesFlag(injury.notes, "nerve_symptoms", "type")}
            onChange={(v) => onUpdate("notes", setSingleNotesFlag(injury.notes, "nerve_symptoms", "type", v))}
          />
        </div>
        <div className="gi-field">
          <label className="gi-label">Is it getting worse?</label>
          <SingleChipRow label="Trend" options={[
            { label: "Yes", value: "worsening" },
            { label: "No", value: "stable" },
            { label: "Not sure", value: "not_sure" },
          ]} value={injury.trend} onChange={(v) => onUpdate("trend", v)} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Did it happen after impact/contact?</label>
          <SingleChipRow label="Impact related" options={YES_NO_UNSURE} value={injury.impact_related} onChange={(v) => onUpdate("impact_related", v)} />
        </div>
      </div>
    );
  }

  if (injury_type === "chest_breathing") {
    const chestFlags = parseNotesFlags(injury.notes, "chest_symptoms");
    const hasNone = chestFlags.includes("none");
    return (
      <div className="gi-followup">
        <div className="gi-field">
          <label className="gi-label">Which symptoms are present?</label>
          <div className="gi-chip-row" role="group" aria-label="Chest or breathing symptoms">
            {[
              { label: "Pain when breathing", value: "breathing_pain" },
              { label: "Shortness of breath", value: "shortness_of_breath" },
              { label: "Chest pain", value: "chest_pain" },
              { label: "Coughing blood", value: "coughing_blood" },
            ].map((flag) => (
              <ChipButton
                key={flag.value}
                label={flag.label}
                selected={chestFlags.includes(flag.value)}
                onClick={() => onUpdate("notes", toggleNotesFlag(setNotesFlags(injury.notes, "chest_symptoms", chestFlags.filter((f) => f !== "none")), "chest_symptoms", flag.value))}
                variant="danger"
              />
            ))}
            <ChipButton
              label="None of these"
              selected={hasNone}
              onClick={() => onUpdate("notes", setNotesFlags(injury.notes, "chest_symptoms", hasNone ? [] : ["none"]))}
            />
          </div>
        </div>
        <div className="gi-field">
          <label className="gi-label">Did it follow impact/contact?</label>
          <SingleChipRow label="Impact" options={YES_NO_UNSURE} value={injury.impact_related} onChange={(v) => onUpdate("impact_related", v)} />
        </div>
        <p className="gi-warning gi-warning-red" role="alert">
          Chest or breathing symptoms may pause normal planning until review.
        </p>
      </div>
    );
  }

  if (injury_type === "surface_injury") {
    return <SurfaceFollowUp injury={injury} onUpdate={onUpdate} />;
  }

  return null;
}

// ── Surface injury branching ─────────────────────────────────────────

function SurfaceFollowUp({
  injury,
  onUpdate,
}: {
  injury: GuidedInjuryState;
  onUpdate: <K extends keyof GuidedInjuryState>(key: K, value: GuidedInjuryState[K]) => void;
}) {
  const st = injury.surface_type;
  if (!st) {
    return (
      <div className="gi-followup">
        <div className="gi-field">
          <label className="gi-label">Is the wound open?</label>
          <SingleChipRow label="Open wound" options={OPEN_WOUND_OPTIONS} value={injury.open_wound} onChange={(v) => onUpdate("open_wound", v)} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Is it still bleeding?</label>
          <SingleChipRow label="Bleeding status" options={BLEEDING_STATUS_OPTIONS} value={injury.bleeding_status} onChange={(v) => onUpdate("bleeding_status", v)} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Signs of infection?</label>
          <InfectionSignsChips injury={injury} onUpdate={onUpdate} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Is it near the eye, mouth, or face?</label>
          <SingleChipRow label="Sensitive area" options={SENSITIVE_AREA_OPTIONS} value={injury.sensitive_area} onChange={(v) => onUpdate("sensitive_area", v)} />
        </div>
      </div>
    );
  }

  if (st === "cut" || st === "laceration") {
    return (
      <div className="gi-followup">
        <div className="gi-field">
          <label className="gi-label">Is it still bleeding?</label>
          <SingleChipRow label="Bleeding status" options={BLEEDING_STATUS_OPTIONS} value={injury.bleeding_status} onChange={(v) => onUpdate("bleeding_status", v)} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Is the wound open?</label>
          <SingleChipRow label="Open wound" options={OPEN_WOUND_OPTIONS} value={injury.open_wound} onChange={(v) => onUpdate("open_wound", v)} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Is it near the eye, mouth, or face?</label>
          <SingleChipRow label="Sensitive area" options={SENSITIVE_AREA_OPTIONS} value={injury.sensitive_area} onChange={(v) => onUpdate("sensitive_area", v)} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Signs of infection?</label>
          <InfectionSignsChips injury={injury} onUpdate={onUpdate} />
        </div>
        <AvoidChips injury={injury} onUpdate={onUpdate} />
      </div>
    );
  }

  if (st === "abrasion") {
    return (
      <div className="gi-followup">
        <div className="gi-field">
          <label className="gi-label">Is the skin broken?</label>
          <SingleChipRow label="Open wound" options={OPEN_WOUND_OPTIONS} value={injury.open_wound} onChange={(v) => onUpdate("open_wound", v)} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Signs of infection?</label>
          <InfectionSignsChips injury={injury} onUpdate={onUpdate} />
        </div>
        <AvoidChips injury={injury} onUpdate={onUpdate} />
      </div>
    );
  }

  if (st === "blister") {
    return (
      <div className="gi-followup">
        <div className="gi-field">
          <label className="gi-label">Is it open or leaking?</label>
          <SingleChipRow label="Open wound" options={OPEN_WOUND_OPTIONS} value={injury.open_wound} onChange={(v) => onUpdate("open_wound", v)} />
        </div>
        <AvoidChips injury={injury} onUpdate={onUpdate} />
      </div>
    );
  }

  if (st === "bruise") {
    return (
      <div className="gi-followup">
        <div className="gi-field">
          <label className="gi-label">Was it from impact?</label>
          <SingleChipRow label="Impact related" options={YES_NO_UNSURE} value={injury.impact_related} onChange={(v) => onUpdate("impact_related", v)} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Is swelling getting worse?</label>
          <SingleChipRow label="Trend" options={[
            { label: "Yes (worsening)", value: "worsening" },
            { label: "No (stable)", value: "stable" },
          ]} value={injury.trend} onChange={(v) => onUpdate("trend", v)} />
        </div>
        <AvoidChips injury={injury} onUpdate={onUpdate} />
      </div>
    );
  }

  if (st === "skin_irritation") {
    return (
      <div className="gi-followup">
        <div className="gi-field">
          <label className="gi-label">Is the skin open / leaking?</label>
          <SingleChipRow label="Open wound" options={OPEN_WOUND_OPTIONS} value={injury.open_wound} onChange={(v) => onUpdate("open_wound", v)} />
        </div>
        <div className="gi-field">
          <label className="gi-label">Signs of infection?</label>
          <InfectionSignsChips injury={injury} onUpdate={onUpdate} />
        </div>
        <AvoidChips injury={injury} onUpdate={onUpdate} />
      </div>
    );
  }

  return null;
}

// ── Infection signs multi-select ─────────────────────────────────────

function InfectionSignsChips({
  injury,
  onUpdate,
}: {
  injury: GuidedInjuryState;
  onUpdate: <K extends keyof GuidedInjuryState>(key: K, value: GuidedInjuryState[K]) => void;
}) {
  function toggle(value: string) {
    const current = injury.infection_signs;
    if (value === "none") {
      onUpdate("infection_signs", current.includes("none") ? [] : ["none"]);
      return;
    }
    const withoutNone = current.filter((s) => s !== "none");
    const next = withoutNone.includes(value)
      ? withoutNone.filter((s) => s !== value)
      : [...withoutNone, value];
    onUpdate("infection_signs", next);
  }

  return (
    <ChipRow
      label="Infection signs"
      options={INFECTION_SIGNS_OPTIONS}
      selected={injury.infection_signs}
      onToggle={toggle}
      variant="danger"
    />
  );
}

// ── Avoid chips ──────────────────────────────────────────────────────

function AvoidChips({
  injury,
  onUpdate,
}: {
  injury: GuidedInjuryState;
  onUpdate: <K extends keyof GuidedInjuryState>(key: K, value: GuidedInjuryState[K]) => void;
}) {
  const chips = getAvoidChipsForInjury(injury);
  if (!chips.length) return null;

  return (
    <div className="gi-field">
      <label className="gi-label">What should be avoided?</label>
      <div className="gi-chip-row" role="group" aria-label="Movements to avoid">
        {chips.map((chip) => (
          <ChipButton
            key={chip}
            label={AVOID_CHIP_LABELS[chip] ?? chip}
            selected={hasAvoidChip(injury.avoid, chip)}
            onClick={() => onUpdate("avoid", toggleAvoidChip(injury.avoid, chip))}
          />
        ))}
      </div>
    </div>
  );
}

// ── Main card component ──────────────────────────────────────────────

interface GuidedInjuryCardProps {
  injury: GuidedInjuryState;
  index: number;
  isActive: boolean;
  onToggleActive: () => void;
  onUpdate: <K extends keyof GuidedInjuryState>(key: K, value: GuidedInjuryState[K]) => void;
  onRemove: () => void;
}

export function GuidedInjuryCard({
  injury,
  index,
  isActive,
  onToggleActive,
  onUpdate,
  onRemove,
}: GuidedInjuryCardProps) {
  const notesFreeText = getNotesFreeText(injury.notes);
  const hasExtraDetail = Boolean(notesFreeText.trim());
  const [notesOpen, setNotesOpen] = useState(hasExtraDetail);
  const [staleNote, setStaleNote] = useState(false);
  const [draftFamily, setDraftFamily] = useState<InjuryFamily | "">("");
  // One progressive "Injury type" picker (family → subtype) replaces the old
  // pair of always-expanded blocks. Start collapsed when a type is already set
  // (e.g. a hydrated or revisited injury) so the card stays compact.
  const [isEditingType, setIsEditingType] = useState(
    !(injury.injury_type && (injury.injury_type !== "surface_injury" || injury.surface_type)),
  );
  const [prevInjury, setPrevInjury] = useState(injury);
  if (injury !== prevInjury) {
    setPrevInjury(injury);
    setIsEditingType(!(injury.injury_type && (injury.injury_type !== "surface_injury" || injury.surface_type)));
  }
  const injuryLabel = truncateForHeader(injury.area) || `Injury ${index + 1}`;
  const compactSummary = truncateForHeader(buildCompactSummary(injury), 80);
  const showWarning = hasGuidedInjuryReviewRisk(injury);
  const hasFollowUp = injury.injury_type !== "";
  const derivedFamily = getFamilyForInjury(injury);
  const activeFamily = derivedFamily || draftFamily;
  const basicsComplete = Boolean(injury.area.trim() && injury.severity && injury.trend);
  const typeComplete = Boolean(injury.injury_type && (injury.injury_type !== "surface_injury" || injury.surface_type));
  const safetyComplete = isSafetyComplete(injury, activeFamily);
  const safetyActive = Boolean(basicsComplete && typeComplete && !safetyComplete);
  const reviewReady = Boolean(basicsComplete && typeComplete && safetyComplete);
  const selectedFamilyOption = activeFamily ? INJURY_FAMILIES.find((f) => f.family === activeFamily) : null;
  const selectedSubtypeLabels = getInjurySubtypeLabels(injury);
  const liveSummary = useMemo(() => {
    const summaryArea = injury.area.trim() || `Injury ${index + 1}`;
    if (!injury.injury_type) return `${summaryArea} · Needs type`;
    if (showWarning) return `${summaryArea} · ${getInjuryTypeLabel(injury)} · Review risk`;
    return [
      summaryArea,
      getInjuryTypeLabel(injury),
      injury.severity ? injury.severity.charAt(0).toUpperCase() + injury.severity.slice(1) : "",
      injury.trend ? injury.trend.charAt(0).toUpperCase() + injury.trend.slice(1) : "",
    ].filter(Boolean).join(" · ");
  }, [index, injury, showWarning]);
  const stepStatus = [
    { key: "basics", label: "Basics", done: basicsComplete, active: !basicsComplete },
    { key: "type", label: "Type", done: typeComplete, active: basicsComplete && !typeComplete },
    { key: "safety", label: "Safety", done: safetyComplete, active: safetyActive },
    { key: "review", label: "Review", done: reviewReady, active: reviewReady },
  ];
  const collapsedStatus = showWarning ? "Review risk" : !injury.injury_type ? "Needs type" : "Complete";
  const stepLabel = !activeFamily
    ? "Step 1 of 3 · Choose injury family"
    : !hasFollowUp
      ? "Step 2 of 3 · Choose injury type"
      : "Step 3 of 3 · Safety details";

  function flagStaleExtraDetail() {
    if (!getNotesFreeText(injury.notes).trim()) {
      return;
    }
    setStaleNote(true);
    setNotesOpen(true);
  }

  function handleTypeSelect(opt: InjuryTypeOption | null) {
    if (!opt) {
      onUpdate("injury_type", "");
      onUpdate("injury_subtypes", []);
      clearTypeSpecificFields(onUpdate);
      onUpdate("notes", stripTaggedNotes(injury.notes, ["red_flags", "dislocation", "nerve_symptoms", "chest_symptoms"]));
      return;
    }

    const isSame =
      injury.injury_type === opt.value &&
      (opt.value !== "surface_injury" ||
        injury.surface_type === (opt.surface_type ?? ""));

    if (isSame) {
      onUpdate("injury_type", "");
      clearTypeSpecificFields(onUpdate);
      onUpdate("notes", stripTaggedNotes(injury.notes, ["red_flags", "dislocation", "nerve_symptoms", "chest_symptoms"]));
      return;
    }

    const currentType = injury.injury_type;
    // The injury is being rewritten as a different type. Free-text extra detail
    // written for the old injury may no longer apply - flag it for the athlete.
    if (currentType && getNotesFreeText(injury.notes).trim()) {
      flagStaleExtraDetail();
    }
    clearTypeSpecificFields(onUpdate);
    onUpdate("injury_type", opt.value);
    onUpdate("surface_type", opt.surface_type ?? "");
    const stripPrefixes: string[] = [];
    if (currentType === "head_impact" && opt.value !== "head_impact") stripPrefixes.push("red_flags");
    if (currentType === "dislocation" && opt.value !== "dislocation") stripPrefixes.push("dislocation");
    if (currentType === "nerve_symptoms" && opt.value !== "nerve_symptoms") stripPrefixes.push("nerve_symptoms");
    if (currentType === "chest_breathing" && opt.value !== "chest_breathing") stripPrefixes.push("chest_symptoms");
    if (stripPrefixes.length) onUpdate("notes", stripTaggedNotes(injury.notes, stripPrefixes));
  }

  function handleFamilySelect(family: InjuryFamily) {
    setDraftFamily(family);
    const currentFamily = getFamilyForInjury(injury);
    if (family === "not_sure") {
      // "Not sure" resolves straight to a type, so collapse the picker.
      handleTypeSelect({ label: "Not sure", value: "unspecified" });
      setIsEditingType(false);
      return;
    }
    if (currentFamily && currentFamily !== family) {
      handleTypeSelect(null);
    }
    // Stay in edit mode; the picker advances to the subtype step now that a
    // family is selected.
  }

  // Return to the family step, discarding the current type/subtype selection.
  function handleChangeCategory() {
    setDraftFamily("");
    handleTypeSelect(null);
    setIsEditingType(true);
  }

  return (
    <section className={`injury-card ${isActive ? "injury-card-active" : ""}`.trim()}>
      <div
        className="injury-card-header injury-card-header-interactive"
        onClick={onToggleActive}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onToggleActive();
          }
        }}
        role="button"
        tabIndex={0}
        aria-expanded={isActive}
      >
        <div className="injury-card-num">{String(index + 1).padStart(2, "0")}</div>
        <div className="injury-card-copy">
          <h3 className="injury-card-title">{injuryLabel}</h3>
          {!isActive ? (
            <p className="injury-card-summary">{compactSummary || liveSummary}</p>
          ) : (
            <p className="injury-card-live-summary">{liveSummary}</p>
          )}
          {!isActive ? (
            <div className="injury-card-pills">
              <span className="injury-card-status-pill">{collapsedStatus}</span>
              {hasExtraDetail ? (
                <span className="injury-card-note-pill" title={notesFreeText}>
                  <svg width="11" height="11" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                    <path d="M2.5 2.5h9M2.5 5.5h9M2.5 8.5h6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                  </svg>
                  Note
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="injury-card-badges">
          {injury.severity ? (
            <span className={`injury-severity-badge injury-severity-badge-${injury.severity}`}>
              {injury.severity.charAt(0).toUpperCase() + injury.severity.slice(1)}
            </span>
          ) : null}
          {injury.trend ? (
            <span className={`injury-trend-badge injury-trend-badge-${injury.trend}`}>
              {TREND_ARROWS[injury.trend] ?? ""}{" "}
              {injury.trend.charAt(0).toUpperCase() + injury.trend.slice(1)}
            </span>
          ) : null}
        </div>
        <div className="injury-card-controls">
          {!isActive ? <button type="button" className="injury-card-edit-btn" onClick={(e) => { e.stopPropagation(); onToggleActive(); }}>Edit</button> : null}
          <button
            type="button"
            className="injury-card-remove-btn"
            onClick={(e) => { e.stopPropagation(); onRemove(); }}
            aria-label="Remove injury"
          >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
            <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          </button>
        </div>
      </div>

      {isActive ? (
        <div className="injury-card-form">
          {/* Step 1 — Describe it */}
          <div className="gi-field">
            <label htmlFor={`gi-area-${index}`} className="gi-label">What happened or what feels wrong?</label>
            <textarea
              id={`gi-area-${index}`}
              value={injury.area}
              onChange={(e) => onUpdate("area", e.target.value)}
              maxLength={GUIDED_INJURY_AREA_MAX}
              placeholder="e.g. hyperextended right knee, rolled ankle, tight hamstring"
              className="gi-area-input"
              rows={3}
            />
            <p className="gi-selection-helper">This is used to identify the injury. Include the body part and what happened.</p>
          </div>

          <div className="gi-step-header">
            <p className="gi-step-track">{stepLabel}</p>
            <div className="gi-stepper" aria-label="Injury intake progress">
              {stepStatus.map((step) => (
                <div key={step.key} className={`gi-stepper-item ${step.active ? "gi-stepper-item-active" : ""} ${step.done ? "gi-stepper-item-done" : ""}`.trim()}>
                  <span className="gi-stepper-dot" aria-hidden="true">{step.done ? "✓" : "•"}</span>
                  <span>{step.label}</span>
                </div>
              ))}
            </div>
          </div>

          {staleNote && hasExtraDetail ? (
            <div className="gi-stale-note gi-stale-note-flash" role="alert">
              <div>
                <strong>Old extra detail is still attached.</strong>
                <span> Review it now or clear it before continuing.</span>
              </div>
              <button
                type="button"
                className="gi-stale-note-clear"
                onClick={() => {
                  onUpdate("notes", setNotesFreeText(injury.notes, ""));
                  setStaleNote(false);
                  setNotesOpen(false);
                }}
              >
                Clear old detail
              </button>
            </div>
          ) : null}

          {/* Injury type — one progressive picker: family → subtype, collapsing
              to a single summary once a type is chosen. */}
          <div className="gi-field">
            <label className="gi-label">Injury type</label>
            <p className="gi-selection-helper">Pick the closest match so we can flag safety risks. Used as a fallback if the description is unclear.</p>

            {typeComplete && !isEditingType ? (
              <div className="gi-selection-summary">
                <p className="gi-selection-title">
                  {selectedSubtypeLabels.length
                    ? `${selectedFamilyOption ? `${selectedFamilyOption.label} · ` : ""}${selectedSubtypeLabels.join(", ")}`
                    : getInjuryTypeLabel(injury)}
                </p>
                <button type="button" className="gi-change-btn" onClick={() => setIsEditingType(true)} aria-expanded={isEditingType}>Change</button>
              </div>
            ) : !activeFamily ? (
              <div className="gi-family-grid" role="radiogroup" aria-label="Injury family">
                {INJURY_FAMILIES.map((family) => (
                  <button
                    key={family.family}
                    type="button"
                    role="radio"
                    aria-checked={false}
                    className="gi-family-card"
                    onClick={() => handleFamilySelect(family.family)}
                  >
                    <span>{family.label}</span>
                    <small>{family.helper}</small>
                  </button>
                ))}
              </div>
            ) : (
              <>
                <div className="gi-selection-summary">
                  <p className="gi-selection-title">{selectedFamilyOption?.label}</p>
                  <button type="button" className="gi-change-btn" onClick={handleChangeCategory}>Change category</button>
                </div>
                <div className="gi-subtype-grid" role="group" aria-label="Injury subtype">
                  {getOptionsForFamily(activeFamily).map((opt) => {
                    if (opt.value === "unspecified") return null;
                    const subtypeKey = getSubtypeKey(opt);
                    const isSelected = (injury.injury_subtypes ?? []).includes(subtypeKey);
                    return (
                      <button key={`${opt.value}-${opt.surface_type ?? ""}`} type="button" aria-pressed={isSelected} className={`gi-chip ${isSelected ? "gi-chip-selected" : ""}`} onClick={() => {
                        const current = injury.injury_subtypes ?? [];
                        const next = isSelected ? current.filter((value) => value !== subtypeKey) : [...current, subtypeKey];
                        onUpdate("injury_subtypes", next);
                        const isPrimary =
                          opt.value === injury.injury_type &&
                          (opt.value !== "surface_injury" || (opt.surface_type ?? "") === injury.surface_type);
                        if (!injury.injury_type) {
                          handleTypeSelect(opt);
                          return;
                        }
                        if (isSelected && isPrimary) {
                          const nextPrimary = next[0];
                          if (!nextPrimary) {
                            handleTypeSelect(null);
                            return;
                          }
                          const nextOpt = getOptionsForFamily(activeFamily).find((candidate) => getSubtypeKey(candidate) === nextPrimary);
                          if (nextOpt) handleTypeSelect(nextOpt);
                        }
                      }}>
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
                {typeComplete ? (
                  <button type="button" className="gi-notes-toggle" onClick={() => setIsEditingType(false)}>Done</button>
                ) : null}
              </>
            )}
          </div>

          {/* Default visible: Severity + Trend */}
          <div className="form-grid">
            <div className="gi-field">
              <label className="gi-label">Current severity</label>
              <div className="injury-severity-chips">
                {GUIDED_INJURY_SEVERITY_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    className={`injury-severity-chip ${injury.severity === opt.value ? `injury-severity-chip-${opt.value}` : ""}`.trim()}
                    aria-pressed={injury.severity === opt.value}
                    onClick={() => onUpdate("severity", injury.severity === opt.value ? "" : opt.value)}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="gi-field">
              <label className="gi-label">Current trend</label>
              <div className="injury-trend-chips">
                {INJURY_TREND_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    className={`injury-trend-chip ${injury.trend === opt.value ? `injury-trend-chip-${opt.value}` : ""}`.trim()}
                    aria-pressed={injury.trend === opt.value}
                    onClick={() => onUpdate("trend", injury.trend === opt.value ? "" : opt.value)}
                  >
                    {TREND_ARROWS[opt.value] ?? ""} {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>


          {/* Progressive follow-up questions */}
          {hasFollowUp ? (
            <div className="gi-safety-panel">
              <FollowUpQuestions injury={injury} family={activeFamily} onUpdate={onUpdate} />
            </div>
          ) : null}

          {/* Review warning */}
          {showWarning ? (
            <div className="gi-review-warning" role="status">
              <svg className="gi-review-warning-icon" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M8 1.5L1 14h14L8 1.5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
                <path d="M8 6v3.5M8 11.5v.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
              </svg>
              <span>Flags here help the coach and admin review risk before release.</span>
            </div>
          ) : null}

          {/* Collapsed notes */}
          {notesOpen ? (
            <div className="gi-field">
              <label htmlFor={`gi-notes-${index}`} className="gi-label">Extra detail</label>
              <textarea
                id={`gi-notes-${index}`}
                value={notesFreeText}
                onChange={(e) => {
                  onUpdate("notes", setNotesFreeText(injury.notes, e.target.value));
                  setStaleNote(false);
                }}
                maxLength={GUIDED_INJURY_NOTES_MAX}
                placeholder="What happened, what irritates it, anything else the planner should know"
                rows={2}
              />
            </div>
          ) : (
            <button
              type="button"
              className="gi-notes-toggle"
              onClick={() => setNotesOpen(true)}
            >
              + Add extra detail
            </button>
          )}
        </div>
      ) : null}
    </section>
  );
}
