"use client";

import Link from "next/link";

import type { UserRole } from "@/lib/types";

type RoleOption = {
  role: Exclude<UserRole, "admin">;
  title: string;
  description: string;
  comingSoonNote?: string;
};

// Admin is intentionally absent: it is never offered at sign-up and stays
// manually assigned only. Athlete is the only live option in private beta;
// coach and gym_owner are visible but disabled until public beta.
const ROLE_OPTIONS: RoleOption[] = [
  {
    role: "athlete",
    title: "Athlete",
    description: "Run Advanced Intake and generate a saved fight camp on your athlete workspace.",
  },
  {
    role: "coach",
    title: "Coach",
    description: "Manage rosters and build camps for the fighters you coach.",
    comingSoonNote: "Coach accounts will be available in public beta.",
  },
  {
    role: "gym_owner",
    title: "Gym Owner",
    description: "Run your gym, oversee coaches, and manage athletes in one place.",
    comingSoonNote: "Gym accounts will be available in public beta.",
  },
];

export function SignupRoleSelection({
  onSelectAthlete,
}: {
  onSelectAthlete: () => void;
}) {
  return (
    <section className="auth-layout">
      <div className="auth-card">
        <div className="auth-header">
          <div>
            <p className="kicker">Create account</p>
            <h2>Choose your role</h2>
          </div>
          <span className="badge status-badge-neutral">Beta</span>
        </div>

        <p className="muted">
          Unlxck is one app for everyone in the camp. Pick how you want to use it. Athlete access is
          open now — coach and gym accounts arrive in public beta.
        </p>

        <ul className="role-card-grid" aria-label="Account roles">
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
                  <RoleCardBody option={option} />
                </button>
              </li>
            );
          })}
        </ul>

        <div className="auth-secondary-links" aria-label="Account help">
          <Link href="/login" className="auth-text-link">
            Already have an account?
          </Link>
        </div>
      </div>

      <div className="auth-rail">
        <div className="hero-panel-copy">
          <p className="eyebrow">Free beta</p>
          <h1>One app for the whole camp.</h1>
          <p>
            Start as an athlete today. Coach and gym tools are on the way, all inside the same Unlxck
            workspace — no separate apps to manage.
          </p>
        </div>
      </div>
    </section>
  );
}

function RoleCardBody({ option }: { option: RoleOption }) {
  return (
    <>
      <span className="role-card-header">
        <span className="role-card-title">{option.title}</span>
        {option.comingSoonNote ? <span className="badge role-card-badge">Coming soon</span> : null}
      </span>
      <span className="role-card-description muted">{option.description}</span>
      {option.comingSoonNote ? (
        <span className="role-card-note">{option.comingSoonNote}</span>
      ) : (
        <span className="role-card-cue" aria-hidden="true">
          Continue →
        </span>
      )}
    </>
  );
}
