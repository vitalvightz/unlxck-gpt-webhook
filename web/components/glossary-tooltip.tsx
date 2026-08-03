"use client";

import { WhyTooltip } from "@/components/why-tooltip";
import { glossaryEntry } from "@/lib/glossary";

/**
 * The "?" that explains a jargon label on a plan surface. Same affordance the
 * intake form uses for its unavailable options, sized down to sit beside a
 * small-caps stat label.
 *
 * Renders NOTHING when the term has no glossary entry, so a caller can pass a
 * label it is already printing (a block tag, a metric label) without first
 * checking whether that particular value needs explaining.
 */
export function GlossaryTooltip({ term }: { term: string | null | undefined }) {
  const entry = glossaryEntry(term);
  if (!entry) {
    return null;
  }
  return (
    <WhyTooltip
      className="glossary-tooltip"
      title={entry.term}
      body={entry.definition}
      triggerLabel="?"
      ariaLabel={`What ${entry.term} means`}
    />
  );
}
