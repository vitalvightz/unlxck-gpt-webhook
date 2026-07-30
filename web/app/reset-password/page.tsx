"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition, type FormEvent } from "react";

import { PasswordStrengthMeter } from "@/components/password-strength-meter";
import { AUTH_FEEDBACK } from "@/lib/auth-feedback";
import { AUTH_LINK_FEEDBACK, clearAuthLinkParams, readAuthLinkStatus } from "@/lib/auth-link";
import { clearPasswordRecovery, hasPasswordRecoveryFor } from "@/lib/password-recovery";
import { evaluatePasswordStrength } from "@/lib/password-strength";
import { getSupabaseBrowserClient } from "@/lib/supabase";

// How long to wait for Supabase to judge a PKCE recovery code before telling
// the athlete we could not reach it.
const CODE_EXCHANGE_TIMEOUT_MS = 8_000;

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
    // that Supabase verified one. An unrelated signed-in session must not open
    // the form — /settings owns ordinary password changes and asks for the
    // current password, which this form deliberately does not.
    //
    // The presence of a credential-shaped param is NOT that proof. supabase-js
    // keeps an existing session when it fails to consume a URL ("Don't remove
    // existing session on URL login failure"), so `?code=arbitrary` on a
    // signed-in browser would otherwise hand over the form. Proof is one of:
    //
    //   1. a PASSWORD_RECOVERY event, which fires only after supabase-js has
    //      validated and stored a recovery session;
    //   2. a stored session whose access token is the one this URL carried,
    //      which means supabase-js minted it from this link;
    //   3. a code that Supabase itself accepts in exchange for a session;
    //   4. a recovery marker for this exact user, written by
    //      PasswordRecoveryRedirect when it saw event 1 on another route —
    //      the case where Supabase sent the link somewhere else entirely.
    const urlAccessToken = linkStatus.kind === "credentials" ? linkStatus.accessToken : null;
    const urlCode = linkStatus.kind === "credentials" ? linkStatus.code : null;
    let settled = false;
    let exchangeTimeoutId: number | undefined;

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
      // A refused attempt spends the marker too, so a stale one cannot sit in
      // the tab waiting to open the form on a later visit.
      clearPasswordRecovery();
    }

    const { data: { subscription } } = client.auth.onAuthStateChange((event, session) => {
      // Proof 1. Deferred by a macrotask inside supabase-js, so this can land
      // after getSession() below has already resolved.
      if (event === "PASSWORD_RECOVERY" && session) {
        markReady();
      }
    });

    // getSession() resolves only after supabase-js has finished parsing the
    // URL, so its answer already reflects any token this link carried.
    client.auth
      .getSession()
      .then(async ({ data: { session } }) => {
        if (settled) {
          return;
        }

        // Proof 2. This session is the one the link minted.
        if (session && urlAccessToken && session.access_token === urlAccessToken) {
          markReady();
          return;
        }

        // Proof 4. The recovery happened on another route and was vouched for
        // there. Bound to this user, so one athlete's recovery can never open
        // the form against another's session.
        if (session && hasPasswordRecoveryFor(session.user?.id)) {
          markReady();
          return;
        }

        // Proof 3. Let Supabase decide whether the code is real. Only reachable
        // under the PKCE flow; an arbitrary code fails here.
        if (urlCode) {
          // Bounded on purpose. auth-js retries a failed fetch with backoff, so
          // an unreachable Supabase would otherwise leave the athlete watching
          // "Verifying your reset link..." forever.
          const outcome = await Promise.race([
            client.auth.exchangeCodeForSession(urlCode).catch(() => null),
            new Promise<"timed-out">((resolve) => {
              exchangeTimeoutId = window.setTimeout(() => resolve("timed-out"), CODE_EXCHANGE_TIMEOUT_MS);
            }),
          ]);
          window.clearTimeout(exchangeTimeoutId);

          if (settled) {
            return;
          }
          if (outcome === "timed-out") {
            failWith(AUTH_FEEDBACK.connectionFailure);
            return;
          }
          if (outcome?.data?.session && !outcome.error) {
            markReady();
            return;
          }
          failWith(AUTH_LINK_FEEDBACK.expired);
          return;
        }

        if (session) {
          // Signed in, but not here via a verified reset link. A new reset link
          // is still the primary way out — someone who forgot their password
          // cannot use /settings, which asks for the current one.
          setCanChangeInSettings(true);
          failWith(AUTH_LINK_FEEDBACK.missing);
          return;
        }
        failWith(urlAccessToken ? AUTH_LINK_FEEDBACK.expired : AUTH_LINK_FEEDBACK.missing);
      })
      .catch(() => {
        if (!settled) {
          failWith(AUTH_FEEDBACK.connectionFailure);
        }
      });

    return () => {
      window.clearTimeout(exchangeTimeoutId);
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

      // The recovery is spent — do not leave a marker that would reopen this
      // form for the rest of the tab's life.
      clearPasswordRecovery();
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
                {/* A new link is the primary way out. Settings is only useful
                    to someone who still knows their current password, which is
                    not the athlete who asked for a reset. */}
                <Link href="/forgot-password" className="cta">
                  Request a new reset link
                </Link>
                {canChangeInSettings ? (
                  <p className="muted">
                    Know your current password?{" "}
                    <Link href="/settings" className="auth-text-link">
                      Change it in Settings
                    </Link>
                    .
                  </p>
                ) : null}
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
