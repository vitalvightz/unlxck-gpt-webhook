"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { dismissBanner, isBannerDismissed } from "@/lib/quick-build-source";

export function QuickBuildRefinementBanner({
  planId,
  planSource,
}: {
  planId: string;
  planSource?: string | null;
}) {
  const isQuickBuild = planSource === "quick_build";
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    if (!isQuickBuild || !planId) return;
    setHidden(isBannerDismissed(planId));
  }, [isQuickBuild, planId]);

  if (!isQuickBuild || hidden) return null;

  function handleDismiss() {
    dismissBanner(planId);
    setHidden(true);
  }

  return (
    <aside className="quick-build-refine-banner" role="region" aria-label="Quick Build refinement">
      <div className="quick-build-refine-banner__body">
        <p className="quick-build-refine-banner__kicker">Quick Build plan</p>
        <h2 className="quick-build-refine-banner__title">Built fast. Make it sharper.</h2>
        <p className="quick-build-refine-banner__copy">
          This plan was built with Quick Build using safe defaults. Open Camp Setup to refine fatigue, injuries, sparring, and goals.
        </p>
      </div>
      <div className="quick-build-refine-banner__actions">
        <Link href="/onboarding?from=quick_build" className="cta quick-build-refine-banner__cta">
          Refine with Camp Setup
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
        Your current plan stays. A new one is only created if you submit Camp Setup.
      </p>
    </aside>
  );
}
