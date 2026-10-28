"use client";

import { usePathname, useRouter } from "next/navigation";
import { useLayoutEffect, useRef, type ReactNode } from "react";

import { prefersReducedMotion } from "@/lib/reduced-motion";
import { useFadeNavigate } from "@/components/fade-through";

/**
 * The page area. Switching pages fades the new one in quickly rather than
 * popping it in a frame; the first page of a visit just appears.
 * Opacity only, so fixed sheets and timers inside are never repositioned.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const fadeNavigate = useFadeNavigate();
  const pageRef = useRef<HTMLDivElement>(null);
  const shownPath = useRef(pathname);

  // Before paint: after it, the new page would show at full strength for a
  // frame first, the very flicker this removes.
  useLayoutEffect(() => {
    if (shownPath.current === pathname) return;
    shownPath.current = pathname;
    // Plan navigation already has a black cover; a second opacity animation
    // exposes the page beneath fixed overlays and makes text shimmer.
    if (pathname?.startsWith("/plans")) return;
    const page = pageRef.current;
    if (!page || typeof page.animate !== "function" || prefersReducedMotion()) return;
    page.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 180, easing: "ease-out" });
  }, [pathname]);

  return <div ref={pageRef} className="page" onClickCapture={event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = (event.target as Element).closest<HTMLAnchorElement>("a[href]");
    if (!link || link.hasAttribute("download") || (link.target && link.target !== "_self")) return;
    const url = new URL(link.href, window.location.href);
    if (url.origin !== window.location.origin || !url.pathname.startsWith("/plans")) return;
    if (url.pathname === window.location.pathname && url.search === window.location.search) return;
    event.preventDefault();
    fadeNavigate(() => router.push(`${url.pathname}${url.search}${url.hash}`));
  }}>{children}</div>;
}
