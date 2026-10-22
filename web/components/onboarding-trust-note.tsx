import { TRUST_INTRO_HEADING, TRUST_POINTS } from "@/lib/trust-copy";

/**
 * Sets expectations at the start of intake: what the camp is built from, that
 * daily check-ins adjust the session rather than rewrite the plan, that a
 * changed session shows its reasons, and that the athlete keeps the final call.
 *
 * Placed before the first question deliberately. An athlete who learns on day
 * nine that the app quietly downgraded their sparring reads it as the app
 * overruling them; one who was told on day zero reads the same change as the
 * thing they signed up for.
 */
export function OnboardingTrustNote() {
  return (
    <details className="onboarding-trust-note">
      <summary className="onboarding-trust-summary" id="onboarding-trust-heading">
        {TRUST_INTRO_HEADING}
      </summary>
      <ul className="onboarding-trust-points" aria-labelledby="onboarding-trust-heading">
        {TRUST_POINTS.map((point) => (
          <li key={point.title} className="onboarding-trust-point">
            <p className="onboarding-trust-point-title">{point.title}</p>
            <p className="onboarding-trust-point-body">{point.body}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}
