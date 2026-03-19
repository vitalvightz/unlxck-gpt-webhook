"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition, type FormEvent } from "react";

import { getSupabaseBrowserClient } from "@/lib/supabase";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    // Supabase detects the recovery token from the URL hash and fires an
    // AUTH_STATE_CHANGE with event "PASSWORD_RECOVERY". We just need to confirm
    // the client has parsed the session before allowing the form to submit.
    let client;
    try {
      client = getSupabaseBrowserClient();
    } catch {
      setError("Supabase is not configured.");
      return;
    }

    const { data: { subscription } } = client.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY") {
        setIsReady(true);
      }
    });

    // Also handle the case where the session is already established from the
    // URL hash before this component mounts.
    client.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setIsReady(true);
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    startTransition(async () => {
      let client;
      try {
        client = getSupabaseBrowserClient();
      } catch (clientError) {
        setError(clientError instanceof Error ? clientError.message : "Supabase is not configured.");
        return;
      }

      const { error: updateError } = await client.auth.updateUser({ password });

      if (updateError) {
        setError(updateError.message);
        return;
      }

      setMessage("Password updated successfully. Redirecting to your account…");
      setTimeout(() => router.push("/plans"), 2000);
    });
  }

  return (
    <section className="auth-layout">
      <div className="auth-rail">
        <div className="hero-panel-copy">
          <p className="eyebrow">Account recovery</p>
          <h1>Choose a new password.</h1>
          <p>Pick a strong password to keep your athlete workspace secure.</p>
        </div>
        <div className="support-panel">
          <p className="kicker">Tips</p>
          <ul className="auth-flow">
            <li>Use at least 8 characters.</li>
            <li>Mix letters, numbers, and symbols.</li>
            <li>Avoid reusing a previous password.</li>
          </ul>
        </div>
      </div>

      <div className="auth-card">
        <div className="auth-header">
          <div>
            <p className="kicker">New password</p>
            <h2>Reset your password</h2>
          </div>
          <span className="badge status-badge-neutral">Secure</span>
        </div>

        {message ? <div className="success-banner">{message}</div> : null}
        {error ? <div className="error-banner">{error}</div> : null}

        {!isReady && !message && !error ? (
          <p className="muted">Verifying your reset link…</p>
        ) : null}

        <form onSubmit={handleSubmit} className="auth-form-grid">
          <div className="field">
            <label htmlFor="password">New password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={8}
              disabled={!isReady}
            />
          </div>
          <div className="field">
            <label htmlFor="confirmPassword">Confirm new password</label>
            <input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
              minLength={8}
              disabled={!isReady}
            />
          </div>

          <div className="form-actions">
            <button type="submit" className="cta" disabled={isPending || !isReady}>
              {isPending ? "Updating…" : "Update password"}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
