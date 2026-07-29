"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition, type FormEvent } from "react";

import { PasswordStrengthMeter } from "@/components/password-strength-meter";
import { AUTH_FEEDBACK } from "@/lib/auth-feedback";
import { AUTH_LINK_FEEDBACK, clearAuthLinkParams, readAuthLinkStatus } from "@/lib/auth-link";
import { evaluatePasswordStrength } from "@/lib/password-strength";
import { getSupabaseBrowserClient } from "@/lib/supabase";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [isReady, setIsReady] = useState(false);
  const [canChangeInSettings, setCanChangeInSettings] = useState(false);
  const passwordStrength = evaluatePasswordStrength(password);
  const passwordsMatch = password === confirmPassword;
  // Read during the first render: supabase-js strips the recovery token from
  // the URL as soon as it initializes, which can happen before this effect runs.
  const [linkStatus] = useState(() =>
    typeof window === "undefined"
      ? ({ kind: "none" } as const)
      : readAuthLinkStatus({ hash: window.location.hash, search: window.location.search }),
  );

  useEffect(() => {
    if (linkStatus.kind === "error") {
      setError(linkStatus.message);
      clearAuthLinkParams();
      return;
    }

    let client;
    try {
      client = getSupabaseBrowserClient();
    } catch {
      setError(AUTH_FEEDBACK.connectionFailure);
      return;
    }

    // This route exists to spend a recovery link, so it unlocks only on proof
    // that one was followed. An unrelated signed-in session must not open the
    // form — /settings owns ordinary password changes and asks for the current
    // password, which this form deliberately does not.
    const cameFromRecoveryLink = linkStatus.kind === "credentials";
    let settled = false;

    function markReady() {
      settled = true;
      setError(null);
      setIsReady(true);
      clearAuthLinkParams();
    }

    // Scrub on the failure paths too. supabase-js only strips the fragment for
    // a token it successfully exchanged, so a stale one would otherwise sit in
    // the address bar and leak into history and the next Referer.
    function failWith(message: string) {
      settled = true;
      setError(message);
      clearAuthLinkParams();
    }

    const { data: { subscription } } = client.auth.onAuthStateChange((event, session) => {
      if (event === "PASSWORD_RECOVERY" || (session && cameFromRecoveryLink)) {
        markReady();
      }
    });

    // getSession() resolves only after supabase-js has finished parsing the
    // URL, so a null session here means the link really did carry nothing
    // usable. Say so straight away instead of stalling behind a timeout.
    client.auth
      .getSession()
      .then(({ data: { session } }) => {
        if (settled) {
          return;
        }
        if (session && cameFromRecoveryLink) {
          markReady();
          return;
        }
        if (session) {
          // Signed in, but not here via a reset link. Point at the route that
          // can actually help rather than sending them round the email loop.
          setCanChangeInSettings(true);
          failWith(AUTH_LINK_FEEDBACK.missing);
          return;
        }
        failWith(cameFromRecoveryLink ? AUTH_LINK_FEEDBACK.expired : AUTH_LINK_FEEDBACK.missing);
      })
      .catch(() => {
        if (!settled) {
          failWith(AUTH_FEEDBACK.connectionFailure);
        }
      });

    return () => {
      subscription.unsubscribe();
    };
  }, [linkStatus]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    if (!passwordStrength.isAcceptable) {
      setError(passwordStrength.feedback);
      return;
    }

    if (!passwordsMatch) {
      setError("Passwords do not match.");
      return;
    }

    startTransition(async () => {
      let client;
      try {
        client = getSupabaseBrowserClient();
      } catch {
        setError("We're having trouble connecting. Please try again in a minute.");
        return;
      }

      const { error: updateError } = await client.auth.updateUser({ password });

      if (updateError) {
        setError(updateError.message);
        return;
      }

      await client.auth.signOut();
      setMessage("Password updated successfully. Redirecting to log in...");
      setTimeout(() => router.replace("/login"), 1500);
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
            <li>Longer uncommon phrases are stronger than predictable patterns.</li>
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

        {message ? (
          <div className="auth-success-state">
            <div className="success-banner">{message}</div>
          </div>
        ) : !isReady ? (
          // The link either failed or has not been verified yet. Showing the
          // password fields here would only offer a form that cannot submit.
          <div className="auth-form-grid">
            {error ? (
              <>
                <div className="error-banner" role="alert" aria-live="assertive" aria-atomic="true">
                  {error}
                </div>
                {canChangeInSettings ? (
                  <Link href="/settings" className="cta cta-secondary">
                    Change your password in Settings
                  </Link>
                ) : null}
                <Link href="/forgot-password" className="cta cta-secondary">
                  Request a new reset link
                </Link>
              </>
            ) : (
              <p className="muted" role="status" aria-live="polite">
                Verifying your reset link...
              </p>
            )}
          </div>
        ) : (
          <>
            {error ? (
              <div className="error-banner" role="alert" aria-live="assertive" aria-atomic="true">
                {error}
              </div>
            ) : null}

            <form onSubmit={handleSubmit} className="auth-form-grid">
              <input
                type="text"
                name="username"
                autoComplete="username"
                className="sr-only"
                tabIndex={-1}
                aria-hidden="true"
              />
              <div className="field">
                <label htmlFor="password">New password</label>
                <input
                  id="password"
                  name="newPassword"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  minLength={8}
                />
                <PasswordStrengthMeter strength={passwordStrength} />
              </div>
              <div className="field">
                <label htmlFor="confirmPassword">Confirm new password</label>
                <input
                  id="confirmPassword"
                  name="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  required
                  minLength={8}
                />
                {confirmPassword && !passwordsMatch ? <p className="error-text">Passwords do not match.</p> : null}
              </div>

              <div className="form-actions">
                <button
                  type="submit"
                  className="cta"
                  disabled={isPending || !passwordStrength.isAcceptable || !passwordsMatch}
                >
                  {isPending ? "Updating..." : "Update password"}
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </section>
  );
}
