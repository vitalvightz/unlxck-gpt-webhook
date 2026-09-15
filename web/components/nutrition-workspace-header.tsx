import Link from "next/link";
import { useTranslations as useAppTranslations } from "next-intl";


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
    const appText = useAppTranslations("AppText");
  return (
    <div className="section-heading">
      <div className="athlete-motion-slot athlete-motion-header">
        <p className="kicker">{appText("text_32b42843ad67")}</p>
        <h1>{title}</h1>
        <p className="muted">{description}</p>
      </div>
      <div className="status-card athlete-motion-slot athlete-motion-status">
        <p className="status-label">{appText("text_374d1c582c2a")}</p>
        <h2 className="plan-summary-title">{athleteName}</h2>
        <div className="plan-summary-actions nutrition-inline-actions">
          <Link href="/onboarding" className="ghost-button">{appText("text_2cd602ade4a6")}</Link>
          <Link href="/settings" className="ghost-button">{appText("text_74a883a037bc")}</Link>
        </div>
      </div>
    </div>
  );
}
