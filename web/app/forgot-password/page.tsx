"use client";

import Link from "next/link";
import { useState, useTransition, type FormEvent } from "react";

import { getSupabaseBrowserClient } from "@/lib/supabase";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    startTransition(async () => {
      let client;
      try {
        client = getSupabaseBrowserClient();
      } catch (clientError) {
        setError(clientError instanceof Error ? clientError.message : "Supabase is not configured.");
        return;
      }

      const { error: resetError } = await client.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/reset-password`,
      });

      if (resetError) {
        setError(resetError.message);
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

              <div className="form-actions">
                <button type="submit" className="cta" disabled={isPending}>
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
