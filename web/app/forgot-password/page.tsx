"use client";

import Link from "next/link";
import { useCallback, useState, useTransition, type FormEvent } from "react";

import { isTurnstileConfigured, TurnstileChallenge } from "@/components/turnstile-challenge";
import { AUTH_FEEDBACK, getPasswordResetErrorMessage } from "@/lib/auth-feedback";
import { buildAuthRedirectUrl } from "@/lib/site-url";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const CAPTCHA_REQUIRED_MESSAGE = "Complete the security check, then try again.";
const CAPTCHA_UNAVAILABLE_MESSAGE = "The security check could not load. Refresh the page and try again.";

export default function ForgotPasswordPage() {
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

      setMessage("If an account exists for that email, you'll receive a password reset link shortly.");
    });
  }

  return (
    <section className="auth-layout">
      <div className="auth-rail">
        <div className="hero-panel-copy">
          <p className="eyebrow">Account recovery</p>
          <h1>Reset your password.</h1>
          <p>Enter your email address and we&apos;ll send you a link to reset your password.</p>
        </div>
        <div className="support-panel">
          <p className="kicker">Steps</p>
          <ol className="auth-flow">
            <li>Enter the email address linked to your account.</li>
            <li>Check your inbox for a reset link.</li>
            <li>Follow the link to choose a new password.</li>
          </ol>
        </div>
      </div>

      <div className="auth-card">
        <div className="auth-header">
          <div>
            <p className="kicker">Password reset</p>
            <h2>Forgot your password?</h2>
          </div>
          <span className="badge status-badge-neutral">Secure</span>
        </div>

        {message ? (
          <div className="auth-success-state">
            <div className="success-banner">{message}</div>
            <div className="support-panel">
              <p className="kicker">Next step</p>
              <p className="muted">Open your email app and look for a message from us. The reset link expires after a short window, so use it soon.</p>
            </div>
            <div className="form-actions">
              <Link href="/login" className="ghost-button">
                Back to log in
              </Link>
            </div>
          </div>
        ) : (
          <>
            {error ? <div className="error-banner">{error}</div> : null}
            <form onSubmit={handleSubmit} className="auth-form-grid">
              <div className="field">
                <label htmlFor="email">Email</label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  placeholder="your@email.com"
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
                  {isPending ? "Sending..." : "Send reset link"}
                </button>
                <Link href="/login" className="ghost-button">
                  Back to log in
                </Link>
              </div>
            </form>
          </>
        )}
      </div>
    </section>
  );
}
