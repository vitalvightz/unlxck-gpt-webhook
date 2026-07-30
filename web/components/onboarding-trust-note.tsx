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
    <aside className="onboarding-trust-note" aria-labelledby="onboarding-trust-heading">
      <div className="form-section-header">
        <p className="kicker">Before you start</p>
        <h2 className="form-section-title" id="onboarding-trust-heading">
          {TRUST_INTRO_HEADING}
        </h2>
      </div>
      <ul className="onboarding-trust-points">
        {TRUST_POINTS.map((point) => (
          <li key={point.title} className="onboarding-trust-point">
            <p className="onboarding-trust-point-title">{point.title}</p>
            <p className="onboarding-trust-point-body">{point.body}</p>
          </li>
        ))}
      </ul>
    </aside>
  );
}
