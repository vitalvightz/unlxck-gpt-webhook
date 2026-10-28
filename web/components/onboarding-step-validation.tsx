export type StepValidationCheck = {
  label: string;
  status: "done" | "pending" | "warning";
  // Where the athlete fixes this item. Unresolved checks with a target render
  // a Fix button so the problem is resolved at the field, not in this list.
  fix?: { fieldId: string; step: number };
};

export function StepValidationPanel({ stepLabel, title, description, checks, onFix, defaultOpen = false }: {
  stepLabel: string;
  title: string;
  description: string;
  checks: StepValidationCheck[];
  onFix?: (check: StepValidationCheck) => void;
  defaultOpen?: boolean;
}) {
  const unresolvedChecks = checks.filter((check) => check.status !== "done");
  return (
    <div role="status" aria-live="polite">
      <details
        className={`support-panel onboarding-validation-panel onboarding-validation-compact ${unresolvedChecks.length ? "onboarding-validation-panel-attention" : "onboarding-validation-panel-ready"}`}
        open={defaultOpen && unresolvedChecks.length > 0 ? true : undefined}
      >
        <summary className="onboarding-validation-summary">
          <span>{stepLabel} checklist</span>
          <span className={`onboarding-validation-badge ${unresolvedChecks.length ? "" : "onboarding-validation-badge-ready"}`}>
            {unresolvedChecks.length ? `${unresolvedChecks.length} to do` : "Ready"}
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
                {check.status !== "done" && check.fix && onFix ? (
                  <>
                    {" "}
                    <button type="button" className="action-link onboarding-validation-fix" onClick={() => onFix(check)}>
                      Fix
                    </button>
                  </>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      </details>
    </div>
  );
}
