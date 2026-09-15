"use client";

import Link from "next/link";
import { useCallback, useState, useTransition, type FormEvent } from "react";

import { isTurnstileConfigured, TurnstileChallenge } from "@/components/turnstile-challenge";
import { AUTH_FEEDBACK, getPasswordResetErrorMessage } from "@/lib/auth-feedback";
import { buildAuthRedirectUrl } from "@/lib/site-url";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { useTranslations as useAppTranslations } from "next-intl";


const CAPTCHA_REQUIRED_MESSAGE = "Complete the security check, then try again.";
const CAPTCHA_UNAVAILABLE_MESSAGE = "The security check could not load. Refresh the page and try again.";

export default function ForgotPasswordPage() {
    const appText = useAppTranslations("AppText");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [captchaResetKey, setCaptchaResetKey] = useState(0);
  const [isPending, startTransition] = useTransition();
  const requiresCaptcha = isTurnstileConfigured();

  const handleCaptchaUnavailable = useCallback(() => {
    setError(CAPTCHA_UNAVAILABLE_MESSAGE);
  }, []);

  function resetCaptcha() {
    if (!requiresCaptcha) {
      return;
    }
    setCaptchaToken(null);
    setCaptchaResetKey((current) => current + 1);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    const captchaTokenForRequest = requiresCaptcha ? captchaToken ?? undefined : undefined;
    if (requiresCaptcha && !captchaTokenForRequest) {
      setError(CAPTCHA_REQUIRED_MESSAGE);
      return;
    }

    startTransition(async () => {
      let client;
      try {
        client = getSupabaseBrowserClient();
      } catch {
        setError(AUTH_FEEDBACK.connectionFailure);
        return;
      }

      let resetResult;
      try {
        resetResult = await client.auth.resetPasswordForEmail(email.trim(), {
          captchaToken: captchaTokenForRequest,
          redirectTo: buildAuthRedirectUrl("/reset-password"),
        });
      } catch {
        resetCaptcha();
        setError(AUTH_FEEDBACK.connectionFailure);
        return;
      }
      resetCaptcha();

      const { error: resetError } = resetResult;
      if (resetError) {
        setError(getPasswordResetErrorMessage(resetError));
        return;
      }

      setMessage(appText("text_59ded8050030"));
    });
  }

  return (
    <section className="auth-layout">
      <div className="auth-rail">
        <div className="hero-panel-copy">
          <p className="eyebrow">{appText("text_2b291cd5cd2f")}</p>
          <h1>{appText("text_8b5cfb67a735")}</h1>
          <p>{appText("text_9bb47a30999c")}</p>
        </div>
        <div className="support-panel">
          <p className="kicker">{appText("text_1de3df70ddf4")}</p>
          <ol className="auth-flow">
            <li>{appText("text_3f2781706652")}</li>
            <li>{appText("text_6c43ba5f7b80")}</li>
            <li>{appText("text_a89132a1957d")}</li>
          </ol>
        </div>
      </div>

      <div className="auth-card">
        <div className="auth-header">
          <div>
            <p className="kicker">{appText("text_359f68acb9b4")}</p>
            <h2>{appText("text_afd25fdf17c7")}</h2>
          </div>
          <span className="badge status-badge-neutral">{appText("text_1bced1d0ce55")}</span>
        </div>

        {message ? (
          <div className="auth-success-state">
            <div className="success-banner">{message}</div>
            <div className="support-panel">
              <p className="kicker">{appText("text_298a9207a732")}</p>
              <p className="muted">{appText("text_9bc0615d2d8b")}</p>
            </div>
            <div className="form-actions">
              <Link href="/login" className="ghost-button">
                {appText("text_30a8b4cdec88")}</Link>
            </div>
          </div>
        ) : (
          <>
            {error ? <div className="error-banner">{error}</div> : null}
            <form onSubmit={handleSubmit} className="auth-form-grid">
              <div className="field">
                <label htmlFor="email">{appText("text_969ccbd3cf63")}</label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  placeholder={appText("text_97af051a28d9")}
                />
              </div>

              <TurnstileChallenge
                action="password_reset"
                onTokenChange={setCaptchaToken}
                onUnavailable={handleCaptchaUnavailable}
                resetKey={captchaResetKey}
              />

              <div className="form-actions">
                <button type="submit" className="cta" disabled={isPending || (requiresCaptcha && !captchaToken)}>
                  {isPending ? appText("text_286a3af7348e") : appText("text_708c5d67ba8e")}
                </button>
                <Link href="/login" className="ghost-button">
                  {appText("text_30a8b4cdec88")}</Link>
              </div>
            </form>
          </>
        )}
      </div>
    </section>
  );
}
