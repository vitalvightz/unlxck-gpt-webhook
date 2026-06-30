"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition, type FormEvent } from "react";

import { useAppSession } from "@/components/auth-provider";
import { PasswordStrengthMeter } from "@/components/password-strength-meter";
import { getMe } from "@/lib/api";
import { getAuthenticatedLandingHref } from "@/lib/auth-routing";
import { evaluatePasswordStrength } from "@/lib/password-strength";
import { ATHLETE_FULL_NAME_MAX } from "@/lib/input-limits";
import { getSiteOrigin } from "@/lib/site-url";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import type { UserRole } from "@/lib/types";

// Roles a user may self-select at sign-up. Admin is intentionally excluded and
// stays manually assigned only. Coach/gym_owner exist in the type system for the
// future but are not yet selectable, so the live path is athlete-only.
const SIGNUP_ROLE_LABELS: Partial<Record<UserRole, string>> = {
  athlete: "Athlete",
};

export function AuthForm({
  mode,
  role,
  onChangeRole,
}: {
  mode: "signup" | "login";
  role?: UserRole;
  onChangeRole?: () => void;
}) {
  const router = useRouter();
  const { isReady, session, me } = useAppSession();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [isMagicLinkPending, startMagicLinkTransition] = useTransition();
  const passwordStrength = evaluatePasswordStrength(password, { fullName, email });
  const isSignupPasswordBlocked = mode === "signup" && !passwordStrength.isAcceptable;

  useEffect(() => {
    if (!isReady) {
      return;
    }
    if (session && me) {
      router.replace(getAuthenticatedLandingHref(me));
    }
  }, [isReady, me, router, session]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    if (mode === "signup" && !passwordStrength.isAcceptable) {
      setError(passwordStrength.feedback);
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

      if (mode === "signup") {
        const siteOrigin = getSiteOrigin();
        // Only athlete is selectable today; persist the chosen role in user
        // metadata so the role foundation is explicit. The backend still owns the
        // authoritative profiles.role (athlete by default, admin only via the
        // service-role tooling), so this never grants elevated access.
        const selectedRole: UserRole = role ?? "athlete";
        const { data, error: signUpError } = await client.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: siteOrigin ? `${siteOrigin}/login` : undefined,
            data: {
              full_name: fullName,
              role: selectedRole,
            },
          },
        });
        if (signUpError) {
          setError(signUpError.message);
          return;
        }
        if (data.session) {
          router.replace("/onboarding");
          return;
        }
        setMessage("Check your email to confirm your account, then log in.");
        return;
      }

      const { data, error: loginError } = await client.auth.signInWithPassword({ email, password });
      if (loginError) {
        setError(loginError.message);
        return;
      }

      const accessToken = data.session?.access_token ?? null;
      if (!accessToken) {
        router.replace("/plans");
        return;
      }

      const nextMe = await getMe(accessToken).catch(() => null);
      router.replace(nextMe ? getAuthenticatedLandingHref(nextMe) : "/plans");
    });
  }

  function handleMagicLink() {
    setMessage(null);
    setError(null);
    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setError("Enter your email above, then request a sign-in link.");
      return;
    }
    startMagicLinkTransition(async () => {
      let client;
      try {
        client = getSupabaseBrowserClient();
      } catch {
        setError("We're having trouble connecting. Please try again in a minute.");
        return;
      }
      const siteOrigin = getSiteOrigin();
      const redirectTo = siteOrigin ? `${siteOrigin}/login` : undefined;
      const { error: otpError } = await client.auth.signInWithOtp({
        email: trimmedEmail,
        options: {
          shouldCreateUser: mode === "signup",
          emailRedirectTo: redirectTo,
        },
      });
      if (otpError) {
        setError(otpError.message);
        return;
      }
      setMessage(`Check ${trimmedEmail} for a one-tap sign-in link.`);
    });
  }

  return (
    <section className="auth-layout">
      <div className="auth-card">
        <div className="auth-header">
          <div>
            <p className="kicker">{mode === "signup" ? "Create account" : "Log in"}</p>
            <h2>{mode === "signup" ? "Start the intake" : "Resume your camp"}</h2>
            {mode === "signup" && role ? (
              <p className="auth-selected-role muted">
                Signing up as <strong>{SIGNUP_ROLE_LABELS[role] ?? role}</strong>
                {onChangeRole ? (
                  <>
                    {" · "}
                    <button type="button" className="auth-text-link auth-inline-link" onClick={onChangeRole}>
                      Change
                    </button>
                  </>
                ) : null}
              </p>
            ) : null}
          </div>
          <span className="badge status-badge-neutral">{mode === "signup" ? "Beta" : "Secure"}</span>
        </div>

        {message ? <div className="success-banner">{message}</div> : null}
        {error ? <div className="error-banner">{error}</div> : null}

        <form onSubmit={handleSubmit} className="auth-form-grid">
          {mode === "signup" ? (
            <div className="field">
              <label htmlFor="fullName">Full name</label>
              <input
                id="fullName"
                name="name"
                autoComplete="name"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                maxLength={ATHLETE_FULL_NAME_MAX}
                required
              />
            </div>
          ) : null}
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              name="email"
              type="email"
              inputMode="email"
              autoComplete="email"
              autoFocus={mode === "login"}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <div className="password-field">
              <input
                id="password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete={mode === "signup" ? "new-password" : "current-password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={8}
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword((prev) => !prev)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                aria-pressed={showPassword}
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
            {mode === "signup" ? <PasswordStrengthMeter strength={passwordStrength} /> : null}
          </div>

          <div className="form-actions auth-form-actions">
            <button type="submit" className="cta" disabled={isPending || isSignupPasswordBlocked}>
              {isPending ? "Working..." : mode === "signup" ? "Create account" : "Log in"}
            </button>
            <button
              type="button"
              className="secondary-button auth-magic-link-button"
              onClick={handleMagicLink}
              disabled={isPending || isMagicLinkPending}
            >
              {isMagicLinkPending
                ? "Sending link..."
                : mode === "signup"
                  ? "Email sign-in link"
                  : "Email sign-in link"}
            </button>
            <div className="auth-secondary-links" aria-label="Account help">
              <Link href={mode === "signup" ? "/login" : "/signup"} className="auth-text-link">
                {mode === "signup" ? "Already have an account?" : "Need an account?"}
              </Link>
              {mode === "login" ? (
                <Link href="/forgot-password" className="auth-text-link">
                  Forgot password?
                </Link>
              ) : null}
            </div>
          </div>
        </form>
      </div>

      <div className="auth-rail">
        <div className="hero-panel-copy">
          <p className="eyebrow">{mode === "signup" ? "Free beta" : "Athlete access"}</p>
          <h1>{mode === "signup" ? "Build your camp inside UNLXCK." : "Re-enter the fight camp control room."}</h1>
          <p>
            {mode === "signup"
              ? "Create your account, complete Advanced Intake, and generate a saved fight camp."
              : "Resume intake, review today, and reopen saved plans from one athlete workspace."}
          </p>
        </div>
        <div className="auth-rail-command-strip" role="region" aria-label="Workspace signals">
          <span>Today</span>
          <strong>Check-in and plan review</strong>
          <span>History saved</span>
        </div>
        <details className="auth-rail-extras">
          <summary>What&apos;s inside the workspace</summary>
          <div className="auth-rail-extras-body">
            <div className="support-panel">
              <p className="kicker">Flow</p>
              <ol className="auth-flow">
                <li>Sign in once and keep your intake on your athlete profile.</li>
                <li>Resume the intake draft whenever you return.</li>
                <li>Generate and reopen saved plans from the same workspace.</li>
              </ol>
            </div>
            <div className="support-panel auth-preview-panel">
              <div className="form-section-header">
                <p className="kicker">Inside the workspace</p>
                <h2 className="form-section-title">Pick up where you left off</h2>
              </div>
              <div className="auth-preview-stack">
                <div className="auth-preview-item">
                  <span className="label">Intake</span>
                  <p className="muted">Draft steps stay attached to your athlete profile, so you can resume instead of restarting.</p>
                </div>
                <div className="auth-preview-item">
                  <span className="label">Saved plans</span>
                  <p className="muted">The latest camp reopens fast, with plan history still in reach.</p>
                </div>
                <div className="auth-preview-item">
                  <span className="label">Nutrition</span>
                  <p className="muted">Readiness, weight setup, and plan history stay connected in one workflow.</p>
                </div>
              </div>
            </div>
            <div className="support-panel">
              <p className="kicker">Why athletes keep using it</p>
              <ul className="summary-list">
                <li>Every generated camp stays saved to the athlete account.</li>
                <li>The same workspace holds intake, nutrition, and plan history.</li>
                <li>Mobile-friendly access makes it easier to reopen camps between sessions.</li>
              </ul>
            </div>
          </div>
        </details>
      </div>
    </section>
  );
}
