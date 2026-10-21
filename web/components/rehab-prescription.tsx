import type { ReactNode } from "react";
import type { StructuredBlock } from "@/lib/types";
import { getRehabExerciseGuide, REHAB_RANGES, rehabRestrictionText } from "@/lib/rehab-exercise-guide";

/** Rehab stop_rules also contain dose/range limits, not only symptom triggers. */
export function RehabExerciseLimits({ rules, compact = false }: { rules: string[]; compact?: boolean }) {
  // The guide closes like a plan exercise card: the red stop label over its list.
  if (compact) return <div className="sp-block-aside rehab-guide-safety" data-kind="stop">
    <span className="sp-stat-label">Safety limits</span>
    <ul className="sp-cues">{rules.map(rule => <li key={rule}>{rule}</li>)}</ul>
  </div>;
  return <div className="ex-detail-stop">
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    </svg>
    <div><span className="sp-stat-label">Exercise limits</span>
      <ul className="sp-cues">{rules.map(rule => <li key={rule}>{rule}</li>)}</ul>
    </div>
  </div>;
}

/** Display the approved fields only; never derive a dose from bank metadata. */
export function RehabPrescription({ block, compact = false }: { block: StructuredBlock; compact?: boolean }) {
  if (block.block_type !== "rehab") return null;
  const equipment = block.drill_snapshot?.equipment;
  const words = (value: string) => value.replaceAll("_", " ");
  // The guide's aside lines read as sentences ("Wall", not "wall").
  const sentence = (value: string) => compact ? value.charAt(0).toUpperCase() + value.slice(1) : value;
  const resistance = block.resistance?.mode === "bodyweight" ? "Bodyweight only · no added resistance"
    : block.resistance?.mode === "external_kg" && typeof block.resistance.kg === "number"
      ? `${block.resistance.kg} kg` : null;
  const rows = [
    ...(!compact && block.dose && Object.keys(block.dose).length === 0
      ? [{ label: "Prescription", text: "Self-paced · follow the instructions above" }] : []),
    ...(equipment ? [{ label: "Equipment", text: equipment.length ? sentence(equipment.map(words).join(", ")) : "No equipment needed" }] : []),
    ...(resistance ? [{ label: "Resistance", text: resistance }] : []),
    ...(block.range_choice ? [{ label: "Range", text: REHAB_RANGES[block.range_choice] ?? words(block.range_choice) }] : []),
    ...(!compact && block.frequency === "daily" ? [{ label: "Frequency", text: "Once daily" }] : []),
  ];
  return <>
    {rows.map(row => <p className="sp-block-aside" key={row.label}>
      <span className="sp-stat-label">{row.label}</span>{compact ? <span>{row.text}</span> : row.text}
    </p>)}
    {!compact && block.mandatory_restrictions?.length ? <div className="sp-block-aside">
      <span className="sp-stat-label">Restrictions</span>
      <ul className="sp-cues">{block.mandatory_restrictions.map(rule => <li key={rule}>{rehabRestrictionText(rule)}</li>)}</ul>
    </div> : null}
  </>;
}

/** Banked rehab exercise sheet, with or without a demo; all text is approved
 * content, split into steps rather than rewritten or generated. It reuses the
 * plan exercise card's demo, stat tiles, cue panel and closing asides. */
export function RehabExerciseGuide({ block, demo, children }: { block: StructuredBlock; demo?: ReactNode; children?: ReactNode }) {
  const guide = getRehabExerciseGuide(block);
  const measured = guide.metrics.some(metric => metric.label !== "Frequency");
  const frequency = guide.metrics.find(metric => metric.label === "Frequency");
  return <div className="injury-sheet-body ex-detail rehab-guide sp-block-embedded">
    {demo ? <div className="rehab-guide-demo">{demo}</div> : null}
    {guide.selfPaced || (!measured && frequency) ? <p className="ex-detail-summary rehab-guide-pace">
      {[guide.selfPaced ? "Self-paced" : null, frequency?.value].filter(Boolean).join(" · ")}
    </p> : null}
    {measured ? <div className="sp-block-stats rehab-guide-dose" data-count={guide.metrics.length} role="group" aria-label="Exercise prescription">
      {guide.metrics.map(metric => <span key={metric.label} className="sp-stat">
        <span className="sp-stat-label">{metric.label}</span>{metric.value}
      </span>)}
    </div> : null}
    {guide.steps.length ? <section className="rehab-guide-how" aria-label="How to perform">
      <span className="sp-stat-label">How to perform</span>
      <ol>{guide.steps.map(step => <li key={step}>{step}</li>)}</ol>
    </section> : null}
    <div className="sp-block-asides rehab-guide-requirements">
      <RehabPrescription block={block} compact />
      {guide.safety.length ? <RehabExerciseLimits rules={guide.safety} compact /> : null}
    </div>
    {children}
  </div>;
}
