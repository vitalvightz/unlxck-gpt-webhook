"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { dismissBanner, isBannerDismissed, isQuickBuildPlan } from "@/lib/quick-build-source";

export function QuickBuildRefinementBanner({ planId }: { planId: string }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!planId) return;
    if (!isQuickBuildPlan(planId)) return;
    if (isBannerDismissed(planId)) return;
    setVisible(true);
  }, [planId]);

  if (!visible) return null;

  function handleDismiss() {
    dismissBanner(planId);
    setVisible(false);
  }

  return (
    <aside className="quick-build-refine-banner" role="region" aria-label="Quick Build refinement">
      <div className="quick-build-refine-banner__body">
        <p className="quick-build-refine-banner__kicker">Quick Build plan</p>
        <h2 className="quick-build-refine-banner__title">Built fast. Make it sharper.</h2>
        <p className="quick-build-refine-banner__copy">
          This plan was built with Quick Build using safe defaults. Run Advanced Intake to refine fatigue, injuries, sparring, and goals.
        </p>
      </div>
      <div className="quick-build-refine-banner__actions">
        <Link href="/onboarding?from=quick_build" className="cta quick-build-refine-banner__cta">
          Refine with Advanced Intake
        </Link>
        <button
          type="button"
          className="ghost-button quick-build-refine-banner__dismiss"
          onClick={handleDismiss}
        >
          Keep current plan
        </button>
      </div>
      <p className="quick-build-refine-banner__note">
        Your current plan stays. A new one is only created if you submit Advanced Intake.
      </p>
    </aside>
  );
}
