"use client";

import Link from "next/link";

/**
 * Phone-only Get started bar that slides up from the bottom while neither the
 * hero nor the closing CTA is on screen, so the primary action stays one tap
 * away. Hidden (and inert) whenever another Get started is visible.
 */
export function LandingStickyCta({ label, visible }: Readonly<{ label: string; visible: boolean }>) {
  return (
    <div className="public-sticky-cta" data-visible={visible} aria-hidden={!visible} inert={!visible}>
      <Link href="/signup" className="cta public-hero-cta public-sticky-cta-button">
        <span>{label}</span>
        <svg className="public-cta-arrow" viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
          <path d="M4 10h11m-4.5-4.5L15 10l-4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </Link>
    </div>
  );
}
