import {
  PRIVATE_TRIAL_CHECKS,
  PRIVATE_TRIAL_CLOSING,
  PRIVATE_TRIAL_DUTIES,
  PRIVATE_TRIAL_INTRO,
  PRIVATE_TRIAL_TITLE,
} from "@/lib/private-trial";

/**
 * The private trial briefing itself, with no acknowledgement and no navigation.
 *
 * Rendered twice: once inside the signup gate, where the tester has to confirm
 * it, and once in Settings, where it stays readable for the rest of the trial.
 * Both render the same words — a tester who half-remembers the screen from
 * signup should find exactly it again, not a paraphrase.
 *
 * Bullets rather than prose is the whole point: this is read once, on a phone,
 * by someone who wants to get to their plan.
 */
export function PrivateTrialGuide({
  headingId,
  showTitle = true,
}: {
  headingId: string;
  /** Settings already titles the section, so it suppresses the banner heading. */
  showTitle?: boolean;
}) {
  return (
    <div className="private-trial-guide">
      {showTitle ? (
        <h1 className="private-trial-title" id={headingId}>
          {PRIVATE_TRIAL_TITLE}
        </h1>
      ) : null}
      <p className="private-trial-intro">{PRIVATE_TRIAL_INTRO}</p>

      <section className="private-trial-section" aria-labelledby={`${headingId}-duties`}>
        <h2 className="private-trial-section-title" id={`${headingId}-duties`}>
          During the trial
        </h2>
        <ul className="private-trial-list">
          {PRIVATE_TRIAL_DUTIES.map((duty) => (
            <li key={duty}>{duty}</li>
          ))}
        </ul>
      </section>

      <section className="private-trial-section" aria-labelledby={`${headingId}-checks`}>
        <h2 className="private-trial-section-title" id={`${headingId}-checks`}>
          Please check
        </h2>
        <ul className="private-trial-list">
          {PRIVATE_TRIAL_CHECKS.map((check) => (
            <li key={check}>{check}</li>
          ))}
        </ul>
      </section>

      <p className="private-trial-closing">{PRIVATE_TRIAL_CLOSING}</p>
    </div>
  );
}
