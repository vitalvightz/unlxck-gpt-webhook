"use client";

import Image from "next/image";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { type CSSProperties, type ReactNode, useActionState, useEffect, useRef, useState } from "react";

import { type AccessCodeState, submitAccessCode } from "@/app/signup/actions";
import { UnlockGlitchText } from "@/components/unlock-glitch-text";
import { SUPPORT_EMAIL } from "@/lib/legal-documents";
import { usePrefersReducedMotion } from "@/lib/reduced-motion";

import authStyles from "./auth-form.module.css";
import styles from "./access-code-gate.module.css";

type CodeShape = { length: number; numeric: boolean };

// How long "Access granted" holds before the account form takes over.
const GRANTED_HOLD_MS = 1600;

/**
 * /signup's invite-only front door. Shows the access-code screen until the
 * server grants access; when access arrives during this visit it holds the
 * "Access granted" moment briefly, then reveals `children` (the account form).
 */
export function SignupAccess({
  unlocked,
  codeShape,
  children,
}: Readonly<{ unlocked: boolean; codeShape: CodeShape; children: ReactNode }>) {
  const reduceMotion = usePrefersReducedMotion();
  // Adjust state while rendering when access flips on (React's pattern for
  // reacting to a prop change), so the gate never flashes the form early.
  const [wasUnlocked, setWasUnlocked] = useState(unlocked);
  const [celebrating, setCelebrating] = useState(false);
  if (unlocked !== wasUnlocked) {
    setWasUnlocked(unlocked);
    if (unlocked) setCelebrating(true);
  }

  useEffect(() => {
    if (!celebrating) return;
    const timer = window.setTimeout(() => setCelebrating(false), reduceMotion ? 500 : GRANTED_HOLD_MS);
    return () => window.clearTimeout(timer);
  }, [celebrating, reduceMotion]);

  if (unlocked && !celebrating) return <>{children}</>;
  return <AccessCodeGate codeShape={codeShape} granted={unlocked} />;
}

function AccessCodeGate({ codeShape, granted }: Readonly<{ codeShape: CodeShape; granted: boolean }>) {
  const t = useTranslations("AccessGate");
  const authT = useTranslations("Auth");
  const [state, formAction, isPending] = useActionState<AccessCodeState, FormData>(submitAccessCode, {
    status: "idle",
    attempt: 0,
  });
  const [code, setCode] = useState("");
  const [focused, setFocused] = useState(true);
  const formRef = useRef<HTMLFormElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Clear the boxes after each wrong code so the next try starts fresh.
  const [seenAttempt, setSeenAttempt] = useState(0);
  if (state.attempt !== seenAttempt) {
    setSeenAttempt(state.attempt);
    if (state.status === "error") setCode("");
  }
  const wrong = state.status === "error" && !isPending && code.length === 0;

  useEffect(() => {
    if (state.status === "error") inputRef.current?.focus();
  }, [state]);

  // Keystrokes that land before the page finishes loading go straight into
  // the input; pick them up once React takes over so nothing typed is lost.
  useEffect(() => {
    const early = inputRef.current?.value ?? "";
    if (early) handleChange(early);
    // Runs once on mount only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleChange(value: string) {
    const pattern = codeShape.numeric ? /[^0-9]/g : /[^0-9a-z]/gi;
    const next = value.replace(pattern, "").toUpperCase().slice(0, codeShape.length);
    setCode(next);
    // A full code submits itself, like a real keypad.
    if (next.length === codeShape.length && !isPending) {
      queueMicrotask(() => formRef.current?.requestSubmit());
    }
  }

  const activeSlot = Math.min(code.length, codeShape.length - 1);

  return (
    <section className={authStyles.layout} aria-labelledby="access-title">
      <div className={`auth-card ${authStyles.content}`} data-granted={granted || undefined}>
        <div className={styles.header}>
          <div className={styles.mark} data-state={granted ? "granted" : "locked"} aria-hidden="true">
            <Image src="/brand/unlxck-one-angle-120.png" alt="" width={40} height={40} priority />
          </div>
          <p className={styles.badge}>
            {granted ? (
              <>
                <span className="sr-only">{t("granted")}</span>
                <UnlockGlitchText key="granted" text={t("granted")} durationMs={600} />
              </>
            ) : (
              t("badge")
            )}
          </p>
          <h1 id="access-title" className={authStyles.title}>
            {granted ? t("grantedTitle") : t("title")}
          </h1>
          <p className={`muted ${styles.lead}`} aria-live="polite">
            {granted ? t("grantedLead") : t("lead")}
          </p>
        </div>

        <form ref={formRef} action={formAction} className={styles.form}>
          <label htmlFor="access-code" className={styles.label}>
            {t("label")}
          </label>
          <div
            key={wrong ? `wrong-${state.attempt}` : "slots"}
            className={styles.slots}
            data-wrong={wrong || undefined}
            data-granted={granted || undefined}
            style={{ gridTemplateColumns: `repeat(${codeShape.length}, minmax(0, 1fr))` }}
          >
            <input
              ref={inputRef}
              id="access-code"
              name="code"
              className={styles.slotInput}
              value={granted ? "•".repeat(codeShape.length) : code}
              onChange={(event) => handleChange(event.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              inputMode={codeShape.numeric ? "numeric" : "text"}
              pattern={codeShape.numeric ? "[0-9]*" : undefined}
              autoComplete="one-time-code"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={codeShape.length}
              required
              autoFocus
              readOnly={granted || isPending}
              aria-invalid={wrong || undefined}
              aria-describedby={wrong ? "access-code-error" : "access-code-hint"}
            />
            {Array.from({ length: codeShape.length }, (_, index) => (
              <span
                key={index}
                className={styles.slot}
                data-filled={granted || index < code.length || undefined}
                data-active={(focused && !granted && !isPending && index === activeSlot) || undefined}
                style={{ "--slot": index } as CSSProperties}
                aria-hidden="true"
              >
                {granted ? "" : code[index] ?? ""}
              </span>
            ))}
          </div>
          <p id="access-code-hint" className="sr-only">
            {t("hint", { length: codeShape.length })}
          </p>
          {wrong ? (
            <p id="access-code-error" className={styles.error} role="alert">
              {t("error")}
            </p>
          ) : null}
          {granted ? null : (
            <button type="submit" className={`cta ${styles.submit}`} disabled={isPending || code.length === 0}>
              {isPending ? t("checking") : t("submit")}
            </button>
          )}
        </form>

        {granted ? null : (
          <>
            <ApplyForBeta />

            <Link href="/login" className={`auth-text-link ${authStyles.accountLink}`}>
              {authT("alreadyAccount")}
            </Link>
          </>
        )}
      </div>
    </section>
  );
}

/**
 * "Apply for beta" as a choice of how to send the email. A bare mailto link
 * does nothing on computers without a default mail app (common with webmail),
 * so Gmail's compose page and a copyable address sit alongside it.
 * Applications go to the public support inbox named in the Terms and Privacy
 * Notice.
 */
function ApplyForBeta() {
  const t = useTranslations("AccessGate");
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const subject = encodeURIComponent(t("applySubject"));
  const body = encodeURIComponent(t("applyBody"));
  const mailtoHref = `mailto:${SUPPORT_EMAIL}?subject=${subject}&body=${body}`;
  const gmailHref = `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(SUPPORT_EMAIL)}&su=${subject}&body=${body}`;

  async function copyAddress() {
    try {
      await navigator.clipboard.writeText(SUPPORT_EMAIL);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // The address is printed below, so it can still be selected by hand.
    }
  }

  return (
    <div className={styles.apply}>
      <span className={styles.divider}>{t("noCode")}</span>
      <button
        type="button"
        className={`secondary-button ${authStyles.email}`}
        aria-expanded={open}
        aria-controls="apply-options"
        onClick={() => setOpen((value) => !value)}
      >
        {t("apply")}
      </button>
      {open ? (
        <div id="apply-options" className={styles.applyOptions}>
          <a href={gmailHref} target="_blank" rel="noopener noreferrer" className={styles.applyOption}>
            {t("applyGmail")}
          </a>
          <a href={mailtoHref} className={styles.applyOption}>
            {t("applyEmailApp")}
          </a>
          <button type="button" className={styles.applyOption} onClick={copyAddress} aria-live="polite">
            {copied ? t("applyCopied") : t("applyCopy")}
          </button>
          <p className={styles.applyAddress}>{SUPPORT_EMAIL}</p>
        </div>
      ) : (
        <p className={styles.applyNote}>{t("applyNote")}</p>
      )}
    </div>
  );
}
