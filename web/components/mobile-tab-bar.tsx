"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, type ReactNode } from "react";

import { useAppSession } from "@/components/auth-provider";
import { useGenerationStatus } from "@/components/generation-status-provider";
import { BOTTOM_NAV_ITEMS } from "@/lib/beta-navigation";

const HIDDEN_ROUTES = new Set<string>(["/generate", "/login", "/signup", "/forgot-password", "/reset-password"]);

const TAB_ICONS: Record<string, ReactNode> = {
  "/": (
    <svg viewBox="0 0 20 20" width="20" height="20" fill="none" aria-hidden="true">
      <path d="M3 10.5L10 4l7 6.5V16a1 1 0 0 1-1 1h-3v-4H8v4H4a1 1 0 0 1-1-1v-5.5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  ),
  "/today": (
    <svg viewBox="0 0 20 20" width="20" height="20" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="14" height="13" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M3 8h14M7 2v3M13 2v3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M7 12l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  "/plans": (
    <svg viewBox="0 0 20 20" width="20" height="20" fill="none" aria-hidden="true">
      <rect x="4" y="3" width="12" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M7 7h6M7 10h6M7 13h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
  "/onboarding": (
    <svg viewBox="0 0 20 20" width="20" height="20" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="14" height="13" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M6 8h8M6 11h6M6 14h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
};

/**
 * How far below the layout viewport's bottom edge the visible (visual)
 * viewport ends, as a negative CSS length, or 0.
 *
 * A fixed element is drawn against the layout viewport. iOS can leave the
 * visual viewport scrolled below it (after momentum scroll, the keyboard, or a
 * toolbar change), which floats a `bottom: 0` bar above the screen's edge with
 * content showing underneath. The offset moves it back onto the visible edge.
 * It never lifts the bar (a keyboard shrinking the visual viewport must not
 * push it up), and is ignored while pinch-zoomed.
 */
export function visualViewportBottomOffset(
  layoutHeight: number,
  viewport: { height: number; offsetTop: number; scale: number } | null | undefined,
): number {
  if (!viewport || Math.abs(viewport.scale - 1) > 0.01 || !(layoutHeight > 0)) {
    return 0;
  }
  const gap = Math.round(layoutHeight - (viewport.offsetTop + viewport.height));
  return gap < 0 ? gap : 0;
}

function isActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function MobileTabBar() {
  const t = useTranslations("Navigation");
  const pathname = usePathname();
  const { isReady, session } = useAppSession();
  const { isActive: generationActive } = useGenerationStatus();

  const isAdminRoute = pathname === "/admin" || pathname.startsWith("/admin/");
  const isHidden = !isReady || !session || isAdminRoute || HIDDEN_ROUTES.has(pathname);

  useEffect(() => {
    const { documentElement } = document;
    if (isHidden) {
      delete documentElement.dataset.mobileTabBar;
      return;
    }
    documentElement.dataset.mobileTabBar = generationActive ? "stacked" : "active";
    return () => {
      delete documentElement.dataset.mobileTabBar;
    };
  }, [isHidden, generationActive]);

  useEffect(() => {
    const viewport = window.visualViewport;
    if (isHidden || !viewport) {
      return;
    }
    const root = document.documentElement;
    let frame = 0;
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const offset = visualViewportBottomOffset(window.innerHeight, viewport);
        if (offset === 0) {
          root.style.removeProperty("--visual-viewport-bottom-offset");
        } else {
          root.style.setProperty("--visual-viewport-bottom-offset", `${offset}px`);
        }
      });
    };
    sync();
    viewport.addEventListener("resize", sync);
    viewport.addEventListener("scroll", sync);
    window.addEventListener("scroll", sync, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      viewport.removeEventListener("resize", sync);
      viewport.removeEventListener("scroll", sync);
      window.removeEventListener("scroll", sync);
      root.style.removeProperty("--visual-viewport-bottom-offset");
    };
  }, [isHidden]);

  if (isHidden) {
    return null;
  }

  return (
    <nav className="mobile-tab-bar" aria-label={t("primary")}>
      {BOTTOM_NAV_ITEMS.map((tab) => {
        const active = isActive(pathname, tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`mobile-tab-bar-item${active ? " mobile-tab-bar-item-active" : ""}`}
            aria-current={active ? "page" : undefined}
          >
            <span className="mobile-tab-bar-icon" aria-hidden="true">
              {TAB_ICONS[tab.href]}
            </span>
            <span className="mobile-tab-bar-label">
              {tab.href === "/"
                ? t("overview")
                : tab.href === "/today"
                  ? t("today")
                  : tab.href === "/plans"
                    ? t("plan")
                    : t("campSetup")}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
