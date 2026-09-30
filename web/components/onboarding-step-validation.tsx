export type StepValidationCheck = {
  label: string;
  status: "done" | "pending" | "warning";
};

export function StepValidationPanel({ stepLabel, title, description, checks }: {
  stepLabel: string;
  title: string;
  description: string;
  checks: StepValidationCheck[];
}) {
  const unresolvedChecks = checks.filter((check) => check.status !== "done");
  return (
    <div role="status" aria-live="polite">
      <details className={`support-panel onboarding-validation-panel onboarding-validation-compact ${unresolvedChecks.length ? "onboarding-validation-panel-attention" : "onboarding-validation-panel-ready"}`}>
        <summary className="onboarding-validation-summary">
          <span>{stepLabel} check</span>
          <span className={`onboarding-validation-badge ${unresolvedChecks.length ? "" : "onboarding-validation-badge-ready"}`}>
            {unresolvedChecks.length ? `${unresolvedChecks.length} left` : "Ready"}
          </span>
          <span className="overview-disclosure-chevron" aria-hidden="true" />
        </summary>
        <div className="onboarding-validation-detail">
          <h2 className="form-section-title">{title}</h2>
          <p className="muted">{description}</p>
          <ul className="summary-list onboarding-validation-list">
            {checks.map((check) => (
              <li key={`${check.status}-${check.label}`} className="onboarding-validation-item" data-status={check.status}>
                {check.label}
              </li>
            ))}
          </ul>
        </div>
      </details>
    </div>
  );
}
