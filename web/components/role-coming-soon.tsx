"use client";

import Link from "next/link";

import { RequireAuth } from "@/components/auth-guard";
import { useTranslations as useAppTranslations } from "next-intl";


// Protected placeholder for roles that are not live yet (coach, gym_owner).
// Wrapped in RequireAuth so anonymous visitors are sent to login, and no role
// can actually operate here until the dashboards ship in public beta.
export function RoleComingSoon({
  kicker,
  title,
  message,
}: {
  kicker: string;
  title: string;
  message: string;
}) {
    const appText = useAppTranslations("AppText");
  return (
    <RequireAuth>
      <section className="panel loading-card" role="status">
        <p className="kicker">{kicker}</p>
        <h1>{title}</h1>
        <p className="muted">{message}</p>
        <div className="hero-actions">
          <Link href="/plans" className="cta">
            {appText("text_8382ef3d7c18")}</Link>
        </div>
      </section>
    </RequireAuth>
  );
}
