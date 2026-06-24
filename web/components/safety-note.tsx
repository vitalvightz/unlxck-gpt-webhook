import type { ReactNode } from "react";

import {
  SAFETY_RED_FLAGS,
  SAFETY_RED_FLAG_ACTION,
  SAFETY_RED_FLAG_HEADING,
} from "@/lib/safety-copy";

type SafetyNoteTone = "info" | "warning";

/**
 * Compact, non-noisy safety panel for athlete-facing flows. Renders the
 * disclaimer text inline; pass `showRedFlags` to append an expandable
 * red-flag checklist so the long list stays collapsed by default.
 */
export function SafetyNote({
  children,
  tone = "info",
  showRedFlags = false,
}: Readonly<{
  children: ReactNode;
  tone?: SafetyNoteTone;
  showRedFlags?: boolean;
}>) {
  return (
    <div className={`safety-note safety-note-${tone}`}>
      <p className="safety-note-body">{children}</p>
      {showRedFlags ? <SafetyRedFlags /> : null}
    </div>
  );
}

/** Expandable red-flag list, collapsed by default to keep cards compact. */
export function SafetyRedFlags() {
  return (
    <details className="safety-note-redflags">
      <summary>{SAFETY_RED_FLAG_HEADING}</summary>
      <ul>
        {SAFETY_RED_FLAGS.map((flag) => (
          <li key={flag}>{flag}</li>
        ))}
      </ul>
      <p className="safety-note-redflag-action">{SAFETY_RED_FLAG_ACTION}</p>
    </details>
  );
}
