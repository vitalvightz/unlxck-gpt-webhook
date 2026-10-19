"use client";

import { useEffect, useId, useRef, useState } from "react";

import sheet from "@/components/log-training.module.css";

import { useAppSession } from "@/components/auth-provider";
import { useToast } from "@/components/toast-provider";
import { submitSparringLog } from "@/lib/api";
import { hasHealthDataConsent } from "@/lib/compliance";
import { lockOverlayScroll } from "@/lib/overlay-scroll-lock";
import type {
  SparringHeadContact,
  SparringIntensity,
  SparringLogSource,
  SparringPlannedIntensity,
} from "@/lib/types";

import styles from "./sparring-log-prompt.module.css";

/** What the finished timer, or a manual sparring log, knows about the sparring. */
export type SparringDraft = {
  source: SparringLogSource;
  planId: string | null;
  sessionId: string | null;
  plannedIntensity: SparringPlannedIntensity | null;
  title: string;
  /** Counted by the timer. A manual log has no count, so the athlete sets it. */
  rounds: number | null;
  roundSeconds: number | null;
  /** The manual training record this report details. */
  externalSessionId?: string | null;
  /** A starting answer from the manual log's effort, never sent as planned. */
  suggestedIntensity?: SparringIntensity;
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

function Choice<Value extends string>({
  legend,
  options,
  labels,
  selected,
  onSelect,
}: Readonly<{
  legend: string;
  options: readonly Value[];
  labels: Record<Value, string>;
  selected: Value | undefined;
  onSelect: (value: Value) => void;
}>) {
  return (
    <fieldset className={sheet.fieldset}>
      <legend>{legend}</legend>
      <div className={options.length === 2 ? styles.twoUp : sheet.effortGrid}>
        {options.map((value) => (
          <button key={value} type="button" aria-pressed={selected === value} onClick={() => onSelect(value)}>
            {labels[value]}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

/**
 * The 15-second post-sparring entry: how hard it really was, rounds (from the
 * timer), head contact, and whether the athlete got rocked or dropped. A "yes"
 * shows the safety message straight away and, once saved, opens an admin
 * review server-side. Health data, so it only appears with health consent.
 *
 * It opens as the same bottom sheet as Log training, so it never lengthens
 * Today itself.
 */
export function SparringLogPrompt({
  token,
  draft,
  onDismiss,
  onSaved,
}: {
  token: string;
  draft: SparringDraft;
  onDismiss: () => void;
  /** After a confirmed save, so Today can refresh its safety guidance. */
  onSaved?: () => void;
}) {
  const { me } = useAppSession();
  const { showToast } = useToast();
  const notesId = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  // Kept across retries of the same answers; any change makes it a new report,
  // so a corrected answer (above all a "Yes, rocked") is never swallowed by
  // an earlier request that landed without its response.
  const requestId = useRef<string | null>(null);
  // Orders this report's sets of answers on the server.
  const revision = useRef(0);
  const [intensity, setIntensity] = useState<SparringIntensity | undefined>(
    defaultIntensity(draft.plannedIntensity) ?? draft.suggestedIntensity,
  );
  const [rounds, setRounds] = useState<number | null>(
    draft.rounds === null ? null : Math.min(30, Math.max(0, draft.rounds)),
  );
  const [headContact, setHeadContact] = useState<SparringHeadContact | undefined>();
  const [rocked, setRocked] = useState<"no" | "yes">("no");
  const [notes, setNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedNotice, setSavedNotice] = useState<string | null>(null);
  const [notesOpen, setNotesOpen] = useState(false);
  const consented = hasHealthDataConsent(me);

  useEffect(() => {
    const element = dialog.current;
    if (!consented || !element) return;
    const previous = document.activeElement as HTMLElement | null;
    const release = lockOverlayScroll();
    if (!element.open) element.showModal?.();
    const fit = () => {
      const viewport = window.visualViewport;
      element.style.setProperty("--sheet-height", `${viewport?.height ?? window.innerHeight}px`);
      element.style.setProperty("--sheet-bottom", `${viewport ? Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop) : 0}px`);
    };
    fit();
    window.visualViewport?.addEventListener("resize", fit);
    window.visualViewport?.addEventListener("scroll", fit);
    return () => {
      window.visualViewport?.removeEventListener("resize", fit);
      window.visualViewport?.removeEventListener("scroll", fit);
      release();
      previous?.focus();
    };
  }, [consented]);

  const answer = <Value,>(set: (value: Value) => void) => (value: Value) => {
    requestId.current = null;
    set(value);
  };

  if (!consented) {
    return null;
  }

  async function save() {
    if (!intensity || !headContact) {
      setError("Pick how hard it was and how much head contact you took.");
      return;
    }
    if (rounds === null) {
      setError("Add how many rounds you sparred.");
      return;
    }
    if (!requestId.current) {
      requestId.current = crypto.randomUUID();
      revision.current += 1;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      const result = await submitSparringLog(token, {
        plan_id: draft.planId,
        session_id: draft.sessionId,
        source: draft.source,
        external_session_id: draft.externalSessionId ?? null,
        client_request_id: requestId.current,
        detail_revision: revision.current,
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
      onSaved?.();
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
    <dialog
      ref={dialog}
      className={sheet.dialog}
      aria-label={savedNotice ? "Sparring logged" : "Log your sparring"}
      onCancel={(event) => {
        event.preventDefault();
        if (!isSubmitting) onDismiss();
      }}
    >
      <header className={sheet.header}>
        <div>
          <h2>{savedNotice ? "Sparring logged" : "Log your sparring"}</h2>
          {savedNotice ? null : (
            <p className={sheet.source}>
              {draft.title}
              {draft.externalSessionId ? " · Session saved. This is optional." : " · Takes 15 seconds."}
            </p>
          )}
        </div>
        <button className={sheet.close} type="button" aria-label="Close sparring log" disabled={isSubmitting} onClick={onDismiss}>
          ×
        </button>
      </header>
      {savedNotice ? (
        <div className={sheet.form}>
          <div className={sheet.body}>
            <p className={styles.safety} role="alert">{savedNotice}</p>
          </div>
          <footer className={sheet.actions}>
            <button type="button" className="cta" onClick={onDismiss}>Got it</button>
          </footer>
        </div>
      ) : (
        <form
          className={sheet.form}
          aria-label="Log your sparring"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <fieldset className={styles.questions} disabled={isSubmitting}>
            <div className={sheet.body}>
              <Choice
                legend="How hard was it?"
                options={["light", "medium", "hard"] as const}
                labels={INTENSITY_LABELS}
                selected={intensity}
                onSelect={answer(setIntensity)}
              />
              <div className={styles.rounds} role="group" aria-label="Rounds">
                <span className={styles.roundsLabel}>Rounds</span>
                <button
                  type="button"
                  aria-label="Fewer rounds"
                  disabled={rounds === null || rounds <= 0}
                  onClick={() => answer(setRounds)(Math.max(0, (rounds ?? 0) - 1))}
                >
                  −
                </button>
                <span className={`sparring-log-rounds-value ${styles.roundsValue}`} aria-live="polite" aria-label={rounds === null ? "Rounds not set" : undefined}>
                  {rounds ?? "–"}
                </span>
                <button
                  type="button"
                  aria-label="More rounds"
                  disabled={(rounds ?? 0) >= 30}
                  onClick={() => answer(setRounds)(Math.min(30, (rounds ?? 0) + 1))}
                >
                  +
                </button>
              </div>
              <Choice
                legend="Head contact"
                options={["none", "light", "heavy"] as const}
                labels={HEAD_CONTACT_LABELS}
                selected={headContact}
                onSelect={answer(setHeadContact)}
              />
              <Choice
                legend="Got rocked or dropped?"
                options={["no", "yes"] as const}
                labels={{ no: "No", yes: "Yes" }}
                selected={rocked}
                onSelect={answer(setRocked)}
              />
              {rocked === "yes" ? (
                <p className={styles.safety} role="alert">
                  {ROCKED_SAFETY_COPY}
                </p>
              ) : null}
              <button
                className={sheet.detailsToggle}
                type="button"
                aria-expanded={notesOpen}
                aria-controls={notesId}
                onClick={() => setNotesOpen((open) => !open)}
              >
                Add a note <span aria-hidden="true">{notesOpen ? "−" : "+"}</span>
              </button>
              <label className={styles.notes} hidden={!notesOpen}>
                <span className="sr-only">Notes (optional)</span>
                <textarea
                  id={notesId}
                  value={notes}
                  maxLength={1000}
                  rows={2}
                  placeholder="Who with, what worked, what to fix"
                  onChange={(event) => answer(setNotes)(event.target.value)}
                />
              </label>
            </div>
          </fieldset>
          <footer className={`${sheet.actions} ${styles.actions}`}>
            {error ? (
              <p className={sheet.error} role="alert">
                {error}
              </p>
            ) : null}
            <button type="button" className="ghost-button" disabled={isSubmitting} onClick={onDismiss}>
              Skip
            </button>
            <button type="submit" className="cta" disabled={isSubmitting}>
              {isSubmitting ? "Saving…" : "Save"}
            </button>
          </footer>
        </form>
      )}
    </dialog>
  );
}
