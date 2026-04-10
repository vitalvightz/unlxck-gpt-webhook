import Link from "next/link";

type NutritionWorkspaceHeaderProps = {
  athleteName: string;
  description: string;
  title: string;
};

export function NutritionWorkspaceHeader({
  athleteName,
  description,
  title,
}: NutritionWorkspaceHeaderProps) {
  return (
    <div className="section-heading">
      <div className="athlete-motion-slot athlete-motion-header">
        <p className="kicker">Nutrition &amp; Weight</p>
        <h1>{title}</h1>
        <p className="muted">{description}</p>
      </div>
      <div className="status-card athlete-motion-slot athlete-motion-status">
        <p className="status-label">Athlete</p>
        <h2 className="plan-summary-title">{athleteName}</h2>
        <div className="plan-summary-actions nutrition-inline-actions">
          <Link href="/onboarding" className="ghost-button">Onboarding</Link>
          <Link href="/settings" className="ghost-button">Settings</Link>
        </div>
      </div>
    </div>
  );
}
