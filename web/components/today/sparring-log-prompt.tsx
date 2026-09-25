"use client";

import { useId, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import { useToast } from "@/components/toast-provider";
import { submitSparringLog } from "@/lib/api";
import { hasHealthDataConsent } from "@/lib/compliance";
import type {
  SparringHeadContact,
  SparringIntensity,
  SparringLogSource,
  SparringPlannedIntensity,
} from "@/lib/types";

/** What the finished timer knows about the sparring it just ran. */
export type SparringDraft = {
  source: SparringLogSource;
  planId: string | null;
  sessionId: string | null;
  plannedIntensity: SparringPlannedIntensity | null;
  title: string;
  rounds: number;
  roundSeconds: number | null;
};

/** Shown the moment "Yes" is picked, before saving; the server returns the same. */
export const ROCKED_SAFETY_COPY =
  "No more contact today. If you get a headache, dizziness, nausea, confusion, memory problems " +
  "or blurred vision, stop training and get checked by a medical professional. Tell your coach.";

const INTENSITY_LABELS: Record<SparringIntensity, string> = {
  light: "Light",
  medium: "Medium",
  hard: "Hard",
};

const HEAD_CONTACT_LABELS: Record<SparringHeadContact, string> = {
  none: "None",
  light: "Light",
  heavy: "A lot",
};

/** The plan's intent as the starting answer; the athlete corrects it if needed. */
export function defaultIntensity(planned: SparringPlannedIntensity | null): SparringIntensity | undefined {
  if (planned === "hard") return "hard";
  if (planned === "light" || planned === "technical") return "light";
  if (planned === "contact") return "medium";
  return undefined;
}

function Chips<Value extends string>({
  legend,
  options,
  labels,
  selected,
  disabled,
  onSelect,
}: Readonly<{
  legend: string;
  options: readonly Value[];
  labels: Record<Value, string>;
  selected: Value | undefined;
  disabled: boolean;
  onSelect: (value: Value) => void;
}>) {
  const legendId = useId();
  return (
    <div className="session-feedback-question">
      <p className="session-feedback-legend" id={legendId}>
        {legend}
      </p>
      <div className="feedback-chips" role="group" aria-labelledby={legendId}>
        {options.map((value) => (
          <button
            key={value}
            type="button"
            className={selected === value ? "feedback-chip is-selected" : "feedback-chip"}
            aria-pressed={selected === value}
            disabled={disabled}
            onClick={() => onSelect(value)}
          >
            {labels[value]}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * The 15-second post-sparring entry: how hard it really was, rounds (from the
 * timer), head contact, and whether the athlete got rocked or dropped. A "yes"
 * shows the safety message straight away and, once saved, opens an admin
 * review server-side. Health data, so it only appears with health consent.
 */
export function SparringLogPrompt({
  token,
  draft,
  onDismiss,
}: {
  token: string;
  draft: SparringDraft;
  onDismiss: () => void;
}) {
  const { me } = useAppSession();
  const { showToast } = useToast();
  const notesId = useId();
  const [intensity, setIntensity] = useState<SparringIntensity | undefined>(
    defaultIntensity(draft.plannedIntensity),
  );
  const [rounds, setRounds] = useState(Math.min(30, Math.max(0, draft.rounds)));
  const [headContact, setHeadContact] = useState<SparringHeadContact | undefined>();
  const [rocked, setRocked] = useState<"no" | "yes">("no");
  const [notes, setNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedNotice, setSavedNotice] = useState<string | null>(null);

  if (!hasHealthDataConsent(me)) {
    return null;
  }

  if (savedNotice) {
    return (
      <section className="feedback-card sparring-log-card" aria-label="Sparring logged">
        <p className="session-feedback-title">Sparring logged</p>
        <p className="sparring-log-safety" role="alert">
          {savedNotice}
        </p>
        <div className="feedback-actions">
          <button type="button" className="cta" onClick={onDismiss}>
            Got it
          </button>
        </div>
      </section>
    );
  }

  async function save() {
    if (!intensity || !headContact) {
      setError("Pick how hard it was and how much head contact you took.");
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      const result = await submitSparringLog(token, {
        plan_id: draft.planId,
        session_id: draft.sessionId,
        source: draft.source,
        planned_intensity: draft.plannedIntensity,
        intensity,
        rounds_completed: rounds,
        round_seconds: draft.roundSeconds,
        head_contact: headContact,
        rocked: rocked === "yes",
        notes: notes.trim(),
      });
      // A rocked report only counts once its review is queued. The server
      // writes both atomically; this guards against any response without it.
      if (rocked === "yes" && !result.review_created) {
        setError("Your report wasn't sent. Please try again.");
        return;
      }
      if (result.safety_notice) {
        setSavedNotice(result.safety_notice);
      } else {
        showToast("Sparring logged.", { tone: "success" });
        onDismiss();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save your sparring log.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="feedback-card sparring-log-card" aria-label="Log your sparring">
      <p className="session-feedback-title">Log your sparring</p>
      <p className="muted session-feedback-intro">
        {draft.title} · takes 15 seconds. Your coach and the app use this to manage contact load.
      </p>

      <Chips
        legend="How hard was it?"
        options={["light", "medium", "hard"] as const}
        labels={INTENSITY_LABELS}
        selected={intensity}
        disabled={isSubmitting}
        onSelect={setIntensity}
      />

      <div className="session-feedback-question">
        <p className="session-feedback-legend">Rounds</p>
        <div className="sparring-log-rounds">
          <button
            type="button"
            className="feedback-chip"
            aria-label="Fewer rounds"
            disabled={isSubmitting || rounds <= 0}
            onClick={() => setRounds((value) => Math.max(0, value - 1))}
          >
            −
          </button>
          <span className="sparring-log-rounds-value" aria-live="polite">
            {rounds}
          </span>
          <button
            type="button"
            className="feedback-chip"
            aria-label="More rounds"
            disabled={isSubmitting || rounds >= 30}
            onClick={() => setRounds((value) => Math.min(30, value + 1))}
          >
            +
          </button>
        </div>
      </div>

      <Chips
        legend="Head contact"
        options={["none", "light", "heavy"] as const}
        labels={HEAD_CONTACT_LABELS}
        selected={headContact}
        disabled={isSubmitting}
        onSelect={setHeadContact}
      />

      <Chips
        legend="Got rocked or dropped?"
        options={["no", "yes"] as const}
        labels={{ no: "No", yes: "Yes" }}
        selected={rocked}
        disabled={isSubmitting}
        onSelect={setRocked}
      />
      {rocked === "yes" ? (
        <p className="sparring-log-safety" role="alert">
          {ROCKED_SAFETY_COPY}
        </p>
      ) : null}

      <label className="field sparring-log-notes" htmlFor={notesId}>
        <span className="session-feedback-legend">Notes (optional)</span>
        <textarea
          id={notesId}
          value={notes}
          maxLength={1000}
          rows={2}
          disabled={isSubmitting}
          placeholder="What worked, what to fix"
          onChange={(event) => setNotes(event.target.value)}
        />
      </label>

      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="feedback-actions sparring-log-actions">
        <button type="button" className="ghost-button" disabled={isSubmitting} onClick={onDismiss}>
          Skip
        </button>
        <button type="button" className="cta" disabled={isSubmitting} onClick={() => void save()}>
          {isSubmitting ? "Saving…" : "Save"}
        </button>
      </div>
    </section>
  );
}
