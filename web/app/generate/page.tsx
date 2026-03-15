"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { generatePlan } from "@/lib/api";
import { hydratePlanRequest } from "@/lib/onboarding";
import { PremiumLoadingScreen } from "@/components/premium-loading-screen";

export default function GeneratePage() {
  const router = useRouter();
  const { me, refreshMe, session } = useAppSession();
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    if (!session?.access_token || !me || started) {
      return;
    }
    const payload = hydratePlanRequest(me);
    if (!payload.fight_date || !payload.athlete.technical_style.length) {
      router.replace("/onboarding");
      return;
    }

    setStarted(true);
    generatePlan(session.access_token, payload)
      .then(async (plan) => {
        await refreshMe();
        router.replace(`/plans/${plan.plan_id}`);
      })
      .catch((generationError) => {
        setError(generationError instanceof Error ? generationError.message : "Unable to generate your plan.");
      });
  }, [me, refreshMe, router, session?.access_token, started]);

  return (
    <RequireAuth>
      <PremiumLoadingScreen error={error} />
    </RequireAuth>
  );
}





