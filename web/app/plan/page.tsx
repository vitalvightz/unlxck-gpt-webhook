"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAppSession } from "@/components/auth-provider";
import { getActivePlan } from "@/lib/api";
import { useTranslations as useAppTranslations } from "next-intl";


export default function PlanAliasPage() {
    const appText = useAppTranslations("AppText");
  const router = useRouter();
  const { session, isReady } = useAppSession();

  useEffect(() => {
    let active = true;
    if (!isReady) {
      return () => {
        active = false;
      };
    }
    const token = session?.access_token;
    if (!token) {
      router.replace("/plans");
      return () => {
        active = false;
      };
    }
    void getActivePlan(token)
      .then((plan) => {
        if (active) router.replace(`/plans/${plan.plan_id}`);
      })
      .catch(() => {
        if (active) router.replace("/plans");
      });
    return () => {
      active = false;
    };
  }, [isReady, router, session?.access_token]);

  return (
    <section className="panel loading-card">
      <p className="kicker">{appText("text_fa8ed0bdabdd")}</p>
      <h1>{appText("text_286f2f57803e")}</h1>
      <p className="muted">{appText("text_3bde8f3813d5")}</p>
    </section>
  );
}
