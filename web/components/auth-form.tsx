"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useTransition,
  type FormEvent,
  type ReactNode,
} from "react";

import { useAppSession } from "@/components/auth-provider";
import { PasswordStrengthMeter } from "@/components/password-strength-meter";
import { isTurnstileConfigured, TurnstileChallenge } from "@/components/turnstile-challenge";
import { getMe } from "@/lib/api";
import { AUTH_FEEDBACK, getLoginErrorMessage, getMagicLinkErrorMessage } from "@/lib/auth-feedback";
import { clearAuthLinkParams, readAuthLinkStatus } from "@/lib/auth-link";
import { getAuthenticatedLandingHref } from "@/lib/auth-routing";
import {
  TERMS_CONSENT_LABEL,
  consentCopyForBand,
  provisionalAgeBand,
  validateDateOfBirth,
} from "@/lib/compliance";
import { PRIVACY_HREF, TERMS_HREF } from "@/lib/legal-documents";
import { recordCompliance } from "@/lib/api";
import { evaluatePasswordStrength } from "@/lib/password-strength";
import { ATHLETE_FULL_NAME_MAX } from "@/lib/input-limits";
import { buildAuthRedirectUrl } from "@/lib/site-url";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import type { UserRole } from "@/lib/types";

const SIGNUP_ROLE_LABELS: Partial<Record<UserRole, string>> = {
  athlete: "Athlete",
};

const CAPTCHA_REQUIRED_MESSAGE = "Complete the security check, then try again.";
const CAPTCHA_UNAVAILABLE_MESSAGE = "The security check could not load. Refresh the page and try again.";

export function AuthForm({
  mode,
  role,
  onChangeRole,
  footerSlot,
}: {
  mode: "signup" | "login";
  role?: UserRole;
  onChangeRole?: () => void;
  footerSlot?: ReactNode;
}) {
  const router = useRouter();
  const { isReady, session, me } = useAppSession();
  const emailInputRef = useRef<HTMLInputElement | null>(null);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [healthDataConsent, setHealthDataConsent] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [captchaResetKey, setCaptchaResetKey] = useState(0);
  const [isPending, startTransition] = useTransition();
  const [isMagicLinkPending, startMagicLinkTransition] = useTransition();
  const passwordStrength = evaluatePasswordStrength(password, { fullName, email });
  const requiresCaptcha = isTurnstileConfigured();
  const isSignupPasswordBlocked = mode === "signup" && !passwordStrength.isAcceptable;
  const isCaptchaBlocked = requiresCaptcha && !captchaToken;
  // Client-side courtesy checks only. The backend and a Postgres trigger both
  // reject an under-13 signup, and the server stamps every consent record, so
  // disabling the button here is about giving a clear message — not about being
  // the control.
  const dateOfBirthError = mode === "signup" ? validateDateOfBirth(dateOfBirth) : null;
  // Health-data consent is deliberately NOT part of this condition. Making it a
  // precondition of creating an account would make it conditional, and consent
  // that is a condition of the service is not freely given (UK GDPR Art. 7(4)) —
  // which would invalidate the very Article 9 basis it exists to establish. An
  // athlete can decline it, keep their account, and give it later from Settings.
  const isSignupConsentBlocked =
    mode === "signup" && (dateOfBirthError !== null || !acceptedTerms);
  // Wording only. The band is derived locally from the date being typed so the
  // explanation matches the reader before the profile exists; the server
  // re-derives it from the stored date and owns every actual consequence.
  const consentCopy = consentCopyForBand(provisionalAgeBand(dateOfBirth));

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

  useEffect(() => {
    const linkStatus = readAuthLinkStatus({
      hash: window.location.hash,
      search: window.location.search,
    });
    if (linkStatus.kind === "error") {
      setError(linkStatus.message);
      clearAuthLinkParams();
    }
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    if (mode === "signup" && !passwordStrength.isAcceptable) {
      setError(passwordStrength.feedback);
      return;
    }

    if (mode === "signup") {
      if (dateOfBirthError) {
        setError(dateOfBirthError);
        return;
      }
      if (!acceptedTerms) {
        setError("Accept the Terms of Use to create an account.");
        return;
      }
    }

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

      if (mode === "signup") {
        const selectedRole: UserRole = role ?? "athlete";
        let signUpResult;
        try {
          signUpResult = await client.auth.signUp({
            email,
            password,
            options: {
              captchaToken: captchaTokenForRequest,
              emailRedirectTo: buildAuthRedirectUrl("/login"),
              data: {
                full_name: fullName,
                // Seeds the profile's date of birth on first sign-in and lets a
                // Postgres trigger reject an under-13 signup even when the
                // caller bypasses this form. The server re-reads and re-derives
                // the age band; nothing trusts this value as an age claim.
                date_of_birth: dateOfBirth,
                role: selectedRole,
              },
            },
          });
        } catch {
          resetCaptcha();
          setError(AUTH_FEEDBACK.connectionFailure);
          return;
        }
        resetCaptcha();

        const { data, error: signUpError } = signUpResult;
        if (signUpError) {
          setError(signUpError.message);
          return;
        }
        if (data.session) {
          // Record the acceptances against the new session so the evidence is
          // server-stamped and versioned. If this call fails the account still
          // exists but is not consented, and the compliance gate catches it on
          // the next screen — so a failure here is surfaced, not swallowed.
          try {
            await recordCompliance(data.session.access_token, {
              date_of_birth: dateOfBirth,
              accept_terms: true,
              // Only sent when ticked. Sending `false` would record a
              // withdrawal, and someone who never consented has not withdrawn —
              // those are different facts and the audit trail keeps them apart.
              ...(healthDataConsent ? { health_data_consent: true } : {}),
            });
          } catch (complianceError) {
            setError(
              complianceError instanceof Error
                ? complianceError.message
                : "Your account was created but your consent could not be saved. Sign in to finish setup.",
            );
            return;
          }
          router.replace("/onboarding");
          return;
        }
        setMessage("Check your email to confirm your account, then log in.");
        return;
      }

      let loginResult;
      try {
        loginResult = await client.auth.signInWithPassword({
          email,
          password,
          options: { captchaToken: captchaTokenForRequest },
        });
      } catch {
        resetCaptcha();
        setError(AUTH_FEEDBACK.connectionFailure);
        return;
      }
      resetCaptcha();

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

    const captchaTokenForRequest = requiresCaptcha ? captchaToken ?? undefined : undefined;
    if (requiresCaptcha && !captchaTokenForRequest) {
      setError(CAPTCHA_REQUIRED_MESSAGE);
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
      const redirectTo = buildAuthRedirectUrl("/login");
      let magicLinkResult;
      try {
        magicLinkResult = await client.auth.signInWithOtp({
          email: trimmedEmail,
          options: {
            captchaToken: captchaTokenForRequest,
            shouldCreateUser: mode === "signup",
            emailRedirectTo: redirectTo,
          },
        });
      } catch {
        resetCaptcha();
        setError(AUTH_FEEDBACK.connectionFailure);
        return;
      }
      resetCaptcha();

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
            <p className="kicker">{mode === "signup" ? "Create account" : "Welcome back"}</p>
            <h2>{mode === "signup" ? "Start the intake" : "Continue your camp"}</h2>
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
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
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

          {mode === "signup" ? (
            <>
              <div className="field">
                <label htmlFor="dateOfBirth">Date of birth</label>
                <input
                  id="dateOfBirth"
                  name="bday"
                  type="date"
                  autoComplete="bday"
                  value={dateOfBirth}
                  onChange={(event) => setDateOfBirth(event.target.value)}
                  aria-describedby="dateOfBirthHelp"
                  required
                />
                <p id="dateOfBirthHelp" className="muted auth-consent-help">
                  UNLXCK is for athletes aged 13 and over. Under-18 accounts get extra privacy
                  and safety protections.
                </p>
              </div>

              <div className="field auth-consent-field">
                <label className="auth-consent-row" htmlFor="acceptTerms">
                  <input
                    id="acceptTerms"
                    name="acceptTerms"
                    type="checkbox"
                    checked={acceptedTerms}
                    onChange={(event) => setAcceptedTerms(event.target.checked)}
                    required
                  />
                  <span>
                    {TERMS_CONSENT_LABEL}{" "}
                    <Link href={TERMS_HREF} className="auth-text-link" target="_blank">
                      Read the Terms
                    </Link>
                  </span>
                </label>
              </div>

              {/* Kept as its own affirmative tick, never folded into the Terms:
                  UK GDPR Art. 9(2)(a) consent has to be specific and separate,
                  and a bundled tick would not be valid consent at all. It is
                  also optional — see isSignupConsentBlocked. */}
              <div className="field auth-consent-field">
                <label className="auth-consent-row" htmlFor="healthDataConsent">
                  <input
                    id="healthDataConsent"
                    name="healthDataConsent"
                    type="checkbox"
                    checked={healthDataConsent}
                    onChange={(event) => setHealthDataConsent(event.target.checked)}
                    aria-describedby="healthDataConsentHelp"
                  />
                  <span>{consentCopy.healthConsentLabel}</span>
                </label>
                <p id="healthDataConsentHelp" className="muted auth-consent-help">
                  {consentCopy.healthConsentHelp}{" "}
                  <Link href={PRIVACY_HREF} className="auth-text-link" target="_blank">
                    Read the Privacy Notice
                  </Link>
                </p>
                {healthDataConsent ? null : (
                  <p className="muted auth-consent-help">{consentCopy.declineNote}</p>
                )}
              </div>
            </>
          ) : null}

          <TurnstileChallenge
            action={mode}
            onTokenChange={setCaptchaToken}
            onUnavailable={handleCaptchaUnavailable}
            resetKey={captchaResetKey}
          />

          <div className="form-actions auth-form-actions">
            <button
              type="submit"
              className="cta"
              disabled={
                isPending || isSignupPasswordBlocked || isSignupConsentBlocked || isCaptchaBlocked
              }
            >
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
              disabled={isPending || isMagicLinkPending || isCaptchaBlocked}
            >
              {isMagicLinkPending ? "Sending link…" : "Email sign-in link"}
            </button>
            <div className="auth-secondary-links" aria-label="Account help">
              <Link href={mode === "signup" ? "/login" : "/signup"} className="auth-text-link">
                {mode === "signup" ? "Already have an account?" : "New to UNLXCK? Join the beta"}
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
          <p className="eyebrow">{mode === "signup" ? "Private beta" : "Athlete access"}</p>
          <h1>{mode === "signup" ? "Build your camp inside UNLXCK." : "Pick up where you left off."}</h1>
          {mode === "signup" ? (
            <p>Set up once, then get a fight camp that tells you what to train and adapts as you go.</p>
          ) : null}
        </div>
        {mode === "signup" ? (
          <div className="auth-signup-proof">
            <p className="kicker">What you get</p>
            <ul className="summary-list">
              <li>Know what to train today, built around your fight date.</li>
              <li>Adjust before fatigue becomes failure with daily check-ins.</li>
              <li>Your whole camp stays in one place, so you never start over.</li>
            </ul>
            <p className="muted auth-signup-note">No payment required during the private beta.</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
