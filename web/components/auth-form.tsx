"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition, type FormEvent, type ReactNode } from "react";

import { useAppSession } from "@/components/auth-provider";
import { PasswordStrengthMeter } from "@/components/password-strength-meter";
import { getMe } from "@/lib/api";
import { AUTH_FEEDBACK, getLoginErrorMessage, getMagicLinkErrorMessage } from "@/lib/auth-feedback";
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
  footerSlot,
}: {
  mode: "signup" | "login";
  role?: UserRole;
  onChangeRole?: () => void;
  /** Rendered inside the auth card below the form — e.g. the PWA install
      prompt on login. Keeps page-level concerns out of this component. */
  footerSlot?: ReactNode;
}) {
  const router = useRouter();
  const { isReady, session, me } = useAppSession();
  const emailInputRef = useRef<HTMLInputElement | null>(null);
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

  useEffect(() => {
    if (mode === "login" && window.matchMedia("(min-width: 721px)").matches) {
      emailInputRef.current?.focus();
    }
  }, [mode]);

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
        setError(AUTH_FEEDBACK.connectionFailure);
        return;
      }

      if (mode === "signup") {
        const siteOrigin = getSiteOrigin();
        // Only athlete is currently selectable; persist the chosen role in user
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

      let loginResult;
      try {
        loginResult = await client.auth.signInWithPassword({ email, password });
      } catch {
        setError(AUTH_FEEDBACK.connectionFailure);
        return;
      }

      const { data, error: loginError } = loginResult;
      if (loginError) {
        setError(getLoginErrorMessage(loginError));
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
        setError(AUTH_FEEDBACK.connectionFailure);
        return;
      }
      const siteOrigin = getSiteOrigin();
      const redirectTo = siteOrigin ? `${siteOrigin}/login` : undefined;
      let magicLinkResult;
      try {
        magicLinkResult = await client.auth.signInWithOtp({
          email: trimmedEmail,
          options: {
            shouldCreateUser: mode === "signup",
            emailRedirectTo: redirectTo,
          },
        });
      } catch {
        setError(AUTH_FEEDBACK.connectionFailure);
        return;
      }

      const { error: otpError } = magicLinkResult;
      if (otpError) {
        setError(getMagicLinkErrorMessage(otpError));
        return;
      }
      setMessage(AUTH_FEEDBACK.magicLinkSent);
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
          {mode === "signup" ? <span className="badge status-badge-neutral">Beta</span> : null}
        </div>

        {message ? (
          <div className="success-banner" role="status" aria-live="polite" aria-atomic="true">
            {message}
          </div>
        ) : null}
        {error ? (
          <div className="error-banner" role="alert" aria-live="assertive" aria-atomic="true">
            {error}
          </div>
        ) : null}

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
              ref={emailInputRef}
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
              {isPending
                ? mode === "signup"
                  ? "Creating account…"
                  : "Signing in…"
                : mode === "signup"
                  ? "Create account"
                  : "Log in"}
            </button>
            <button
              type="button"
              className="auth-text-link auth-magic-link-action"
              onClick={handleMagicLink}
              disabled={isPending || isMagicLinkPending}
            >
              {isMagicLinkPending ? "Sending link…" : "Email sign-in link"}
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

        {footerSlot}
      </div>

      <div className="auth-rail">
        <div className="hero-panel-copy">
          <p className="eyebrow">{mode === "signup" ? "Free beta" : "Athlete access"}</p>
          <h1>{mode === "signup" ? "Build your camp inside UNLXCK." : "Enter the UNLXCK fight camp control room."}</h1>
          <p>
            {mode === "signup"
              ? "Create your account, complete Advanced Intake, and generate a saved fight camp."
              : "Resume intake and reopen saved plans from one athlete workspace."}
          </p>
        </div>
        {mode === "signup" ? (
          <div className="auth-signup-proof">
            <p className="kicker">What you get</p>
            <ul className="summary-list">
              <li>A camp built around your schedule and restrictions.</li>
              <li>Daily readiness decisions that adjust training.</li>
              <li>Saved plans and progress in one workspace.</li>
            </ul>
          </div>
        ) : null}
      </div>
    </section>
  );
}
