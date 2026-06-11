"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAppSession } from "@/components/auth-provider";
import { useGenerationStatus } from "@/components/generation-status-provider";

type Tab = {
  href: string;
  label: string;
  icon: ReactNode;
};

const HIDDEN_ROUTES = new Set<string>(["/generate", "/login", "/signup", "/forgot-password", "/reset-password"]);

const TABS: Tab[] = [
  {
    href: "/",
    label: "Overview",
    icon: (
      <svg viewBox="0 0 20 20" width="20" height="20" fill="none" aria-hidden="true">
        <path d="M3 10.5L10 4l7 6.5V16a1 1 0 0 1-1 1h-3v-4H8v4H4a1 1 0 0 1-1-1v-5.5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    href: "/dashboard",
    label: "Today",
    icon: (
      <svg viewBox="0 0 20 20" width="20" height="20" fill="none" aria-hidden="true">
        <rect x="3" y="4" width="14" height="13" rx="2" stroke="currentColor" strokeWidth="1.5" />
        <path d="M3 8h14M7 2v3M13 2v3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M7 12l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    href: "/onboarding",
    label: "Intake",
    icon: (
      <svg viewBox="0 0 20 20" width="20" height="20" fill="none" aria-hidden="true">
        <rect x="3" y="4" width="14" height="13" rx="2" stroke="currentColor" strokeWidth="1.5" />
        <path d="M6 8h8M6 11h6M6 14h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    href: "/nutrition",
    label: "Nutrition",
    icon: (
      <svg viewBox="0 0 20 20" width="20" height="20" fill="none" aria-hidden="true">
        <path d="M10 3v3M7 6h6l-1 11H8L7 6z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    href: "/plans",
    label: "Plans",
    icon: (
      <svg viewBox="0 0 20 20" width="20" height="20" fill="none" aria-hidden="true">
        <rect x="4" y="3" width="12" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
        <path d="M7 7h6M7 10h6M7 13h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function MobileTabBar() {
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

  if (isHidden) {
    return null;
  }

  return (
    <nav className="mobile-tab-bar" aria-label="Primary">
      {TABS.map((tab) => {
        const active = isActive(pathname, tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`mobile-tab-bar-item${active ? " mobile-tab-bar-item-active" : ""}`}
            aria-current={active ? "page" : undefined}
          >
            <span className="mobile-tab-bar-icon" aria-hidden="true">
              {tab.icon}
            </span>
            <span className="mobile-tab-bar-label">{tab.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
