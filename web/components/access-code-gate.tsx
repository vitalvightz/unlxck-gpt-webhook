"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useActionState } from "react";

import { submitAccessCode } from "@/app/signup/actions";
import { SUPPORT_EMAIL } from "@/lib/legal-documents";

import authStyles from "./auth-form.module.css";
import styles from "./access-code-gate.module.css";

/** Invite-only front door for /signup: an access code, or a way to apply. */
export function AccessCodeGate() {
  const t = useTranslations("AccessGate");
  const authT = useTranslations("Auth");
  const [state, formAction, isPending] = useActionState(submitAccessCode, { error: false });
  // Beta applications go to the public support inbox named in the Terms and
  // Privacy Notice.
  const applyHref = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(t("applySubject"))}&body=${encodeURIComponent(t("applyBody"))}`;

  return (
    <section className={authStyles.layout} aria-labelledby="access-title">
      <div className={`auth-card ${authStyles.content}`}>
        <div className="auth-header">
          <div>
            <p className={`kicker ${authStyles.brand}`}>UNLXCK</p>
            <h1 id="access-title" className={authStyles.title}>
              {t("title")}
            </h1>
            <p className={`muted ${styles.lead}`}>{t("lead")}</p>
          </div>
        </div>

        <form action={formAction} className={styles.form}>
          <label htmlFor="access-code" className={styles.label}>
            {t("label")}
          </label>
          <input
            id="access-code"
            name="code"
            className={styles.input}
            inputMode="numeric"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            maxLength={12}
            placeholder={t("placeholder")}
            required
            autoFocus
            aria-invalid={state.error || undefined}
            aria-describedby={state.error ? "access-code-error" : undefined}
          />
          {state.error ? (
            <p id="access-code-error" className={styles.error} role="alert">
              {t("error")}
            </p>
          ) : null}
          <button type="submit" className={`cta ${styles.submit}`} disabled={isPending}>
            {isPending ? t("checking") : t("submit")}
          </button>
        </form>

        <div className={styles.apply}>
          <span className={styles.divider}>{t("noCode")}</span>
          <a href={applyHref} className={`secondary-button ${authStyles.email}`}>
            {t("apply")}
          </a>
          <p className={styles.applyNote}>{t("applyNote")}</p>
        </div>

        <Link href="/login" className={`auth-text-link ${authStyles.accountLink}`}>
          {authT("alreadyAccount")}
        </Link>
      </div>
    </section>
  );
}
