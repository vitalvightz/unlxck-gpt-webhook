"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import type { UserRole } from "@/lib/types";

type RoleOption = {
  role: Exclude<UserRole, "admin">;
  titleKey: string;
  descriptionKey: string;
  comingSoonKey?: string;
};

// Admin is intentionally absent: it is never offered at sign-up and stays
// manually assigned only. Athlete is the only live option in private beta;
// coach and gym_owner are visible but disabled until public beta.
const ROLE_OPTIONS: RoleOption[] = [
  {
    role: "athlete",
    titleKey: "athlete",
    descriptionKey: "athleteDescription",
  },
  {
    role: "coach",
    titleKey: "coach",
    descriptionKey: "coachDescription",
    comingSoonKey: "coachSoon",
  },
  {
    role: "gym_owner",
    titleKey: "gymOwner",
    descriptionKey: "gymDescription",
    comingSoonKey: "gymSoon",
  },
];

export function SignupRoleSelection({
  onSelectAthlete,
}: {
  onSelectAthlete: () => void;
}) {
  const t = useTranslations("Auth");
  return (
    <section className="auth-layout">
      <div className="auth-card">
        <div className="auth-header">
          <div>
            <p className="kicker">{t("createAccount")}</p>
            <h2>{t("chooseRole")}</h2>
          </div>
          <span className="badge status-badge-neutral">Beta</span>
        </div>

        <p className="muted">
          {t("roleIntro")}
        </p>

        <ul className="role-card-grid" aria-label={t("accountRoles")}>
          {ROLE_OPTIONS.map((option) => {
            const isActive = option.role === "athlete";
            const cardClassName = isActive
              ? "role-card role-card-active"
              : "role-card role-card-disabled";

            return (
              <li key={option.role}>
                <button
                  type="button"
                  className={cardClassName}
                  onClick={isActive ? onSelectAthlete : undefined}
                  disabled={!isActive}
                >
                  <RoleCardBody option={option} t={t} />
                </button>
              </li>
            );
          })}
        </ul>

        <div className="auth-secondary-links" aria-label={t("accountHelp")}>
          <Link href="/login" className="auth-text-link">
            {t("alreadyAccount")}
          </Link>
        </div>
      </div>

      <div className="auth-rail">
        <div className="hero-panel-copy">
          <p className="eyebrow">{t("freeBeta")}</p>
          <h1>{t("wholeCampTitle")}</h1>
          <p>{t("wholeCampSummary")}</p>
        </div>
      </div>
    </section>
  );
}

function RoleCardBody({ option, t }: { option: RoleOption; t: ReturnType<typeof useTranslations> }) {
  return (
    <>
      <span className="role-card-header">
        <span className="role-card-title">{t(option.titleKey)}</span>
        {option.comingSoonKey ? <span className="badge role-card-badge">{t("comingSoon")}</span> : null}
      </span>
      <span className="role-card-description muted">{t(option.descriptionKey)}</span>
      {option.comingSoonKey ? (
        <span className="role-card-note">{t(option.comingSoonKey)}</span>
      ) : (
        <span className="role-card-cue" aria-hidden="true">
          {t("continue")} →
        </span>
      )}
    </>
  );
}
