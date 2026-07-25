import type { RehabLabelPolicy, StructuredBlock } from "@/lib/types";

/**
 * Rehab work is only "Rehab" while the body region it targets is actually
 * injured. Once that injury clears, the same drill is prophylactic and reads
 * "Prehab" — even if the athlete is carrying an unrelated injury elsewhere. A
 * cleared hamstring must not keep reading "Rehab" because a quad is sore.
 *
 * Structured blocks carry no injury link, so the match is textual: the server
 * (api/rehab_labels.py) resolves each live injury flag to a body region and
 * ships its match terms; here we scan the block's own words for them. Both
 * render surfaces — Plan detail and Today — go through this one function.
 */

/** Mirrors normalize_match_term in api/rehab_labels.py. Drops parentheticals,
 * lowercases, collapses punctuation to single spaces. */
export function normalizeRehabText(value: unknown): string {
  return String(value ?? "")
    .toLowerCase()
    .replace(/\([^)]*\)/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/** Every word of a block that could name its target region. */
function blockHaystack(block: StructuredBlock): string {
  const parts = [
    block.display_name,
    block.purpose,
    ...(block.coaching_cues ?? []),
    ...(block.substitutions ?? []),
  ];
  return ` ${normalizeRehabText(parts.filter(Boolean).join(" "))} `;
}

export function isRehabBlock(block: StructuredBlock): boolean {
  return String(block.block_type ?? "").trim().toLowerCase() === "rehab";
}

/**
 * Whether a rehab block targets a region the athlete is currently injured in.
 * Terms match on whole-word runs so "hip" cannot fire on "hip hinge cue"'s
 * neighbours or "ship".
 */
function matchesActiveInjury(block: StructuredBlock, policy: RehabLabelPolicy): boolean {
  const haystack = blockHaystack(block);
  return policy.active_regions.some((region) =>
    region.terms.some((term) => term && haystack.includes(` ${term} `)),
  );
}

/**
 * Tag text for a rehab block: "Rehab" while its region is live, else the
 * policy's default. Without a policy (legacy payload, or a surface that never
 * loaded one) everything stays "Rehab" — the honest, unchanged wording.
 */
export function resolveBlockRehabLabel(
  block: StructuredBlock,
  policy: RehabLabelPolicy | null | undefined,
): "Rehab" | "Prehab" {
  if (!policy) {
    return "Rehab";
  }
  if (matchesActiveInjury(block, policy)) {
    return "Rehab";
  }
  return policy.default_mode === "prehab" ? "Prehab" : "Rehab";
}

/**
 * Heading for a session's rehab/mobility summary, given that session's blocks.
 * A session mixing live rehab with cleared prehab is still rehab work overall,
 * so any single live block keeps the whole list on "Rehab". A list with no
 * rehab-typed blocks at all (mobility only) keeps the standing wording — there
 * is no rehab work there to have cleared.
 */
export function resolveRehabSummaryLabel(
  blocks: StructuredBlock[],
  policy: RehabLabelPolicy | null | undefined,
): "Rehab" | "Prehab" {
  const rehabBlocks = blocks.filter(isRehabBlock);
  if (rehabBlocks.length === 0) {
    return "Rehab";
  }
  return rehabBlocks.some((block) => resolveBlockRehabLabel(block, policy) === "Rehab")
    ? "Rehab"
    : "Prehab";
}
