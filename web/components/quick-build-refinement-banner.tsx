"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { dismissBanner, isBannerDismissed } from "@/lib/quick-build-source";
import { useTranslations as useAppTranslations } from "next-intl";


export function QuickBuildRefinementBanner({
  planId,
  planSource,
}: {
  planId: string;
  planSource?: string | null;
}) {
    const appText = useAppTranslations("AppText");
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
    <aside className="quick-build-refine-banner" role="region" aria-label={appText("text_e7062cd7a370")}>
      <div className="quick-build-refine-banner__body">
        <p className="quick-build-refine-banner__kicker">{appText("text_7bd7a1ac425b")}</p>
        <h2 className="quick-build-refine-banner__title">{appText("text_ffc9ab9878cc")}</h2>
        <p className="quick-build-refine-banner__copy">
          {appText("text_ba0600b808ed")}</p>
      </div>
      <div className="quick-build-refine-banner__actions">
        <Link href="/onboarding?from=quick_build" className="cta quick-build-refine-banner__cta">
          {appText("text_bcda9fe5db87")}</Link>
        <button
          type="button"
          className="ghost-button quick-build-refine-banner__dismiss"
          onClick={handleDismiss}
        >
          {appText("text_e371a7b52711")}</button>
      </div>
      <p className="quick-build-refine-banner__note">
        {appText("text_44d11d3b535a")}</p>
    </aside>
  );
}
