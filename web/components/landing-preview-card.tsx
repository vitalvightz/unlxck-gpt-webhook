"use client";

import { useLocale, useTranslations } from "next-intl";
import { type CSSProperties, useEffect, useState } from "react";

import { usePrefersReducedMotion } from "@/lib/reduced-motion";
import { useInView } from "@/lib/use-in-view";

type Phase = "planned" | "adjusted";

// How long the planned session sits on screen before the check-in adjusts it.
const ADJUST_AFTER_MS = 3000;

/**
 * The landing's example Today card. It first shows the session as planned,
 * then, once scrolled into view, plays the adjustment: the readiness call
 * slides in, the heavy bag dose drops, reaction drills are added, and each
 * row is tagged. Under reduced motion it renders the adjusted session.
 */
export function LandingPreviewCard({ className, style }: Readonly<{ className?: string; style?: CSSProperties }>) {
  const t = useTranslations("PublicHome");
  const locale = useLocale();
  const reduceMotion = usePrefersReducedMotion();
  const [ref, seen] = useInView<HTMLElement>({ threshold: 0.6, once: true });
  const [played, setPlayed] = useState(false);

  useEffect(() => {
    if (!seen || reduceMotion) return;
    const timer = window.setTimeout(() => setPlayed(true), ADJUST_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, [seen, reduceMotion]);

  const phase: Phase = reduceMotion || played ? "adjusted" : "planned";
  const adjusted = phase === "adjusted";
  // Minutes are formatted by Intl, so the example session reads naturally in
  // every locale without a translated "min" string per dose.
  const formatMinutes = (minutes: number) =>
    new Intl.NumberFormat(locale, {
      style: "unit",
      unit: "minute",
      unitDisplay: "short",
    }).format(minutes);
  const blocks = [
    {
      name: t("exHeavyBag"),
      sets: adjusted ? 4 : 5,
      minutes: 3,
      change: "down",
      tag: t("tagReduced"),
      delay: 900,
    },
    {
      name: t("exReaction"),
      sets: 3,
      minutes: 2,
      change: "up",
      tag: t("tagAdded"),
      delay: 1700,
      added: true,
    },
    {
      name: t("exShadow"),
      sets: 3,
      minutes: 3,
      change: null,
      tag: t("tagUnchanged"),
      delay: 2500,
    },
  ] as const;

  return (
    <article
      ref={ref}
      className={className ? `public-today-card ${className}` : "public-today-card"}
      style={style}
      data-phase={phase}
      aria-label={t("previewCardLabel")}
    >
      <header className="public-today-head">
        <p className="public-today-eyebrow">{t("todaySession")}</p>
        <span className="public-today-example">{t("example")}</span>
      </header>
      <p className="public-today-title">{t("sessionTitle")}</p>
      <p className="public-today-meta">
        {t("sessionSport")} · {formatMinutes(50)} · {t("previewPlan")}
      </p>
      {/* Parts that exist only once the session is adjusted are hidden from
          assistive tech (and focus) while collapsed, not just visually. */}
      <div className="public-today-collapse public-today-decision-slot" aria-hidden={!adjusted} inert={!adjusted}>
        <div>
          <p className="public-today-decision-row">
            <span className="public-today-decision">{t("decision")}</span>
            <span className="public-today-reason">{t("reasonText")}</span>
          </p>
        </div>
      </div>
      <ol className="public-today-blocks">
        {blocks.map((block) => (
          <li
            key={block.name}
            className={"added" in block ? "public-today-collapse public-today-block-slot" : "public-today-block-slot"}
            aria-hidden={"added" in block && !adjusted ? true : undefined}
            inert={"added" in block && !adjusted}
            style={{ "--step-delay": `${block.delay}ms` } as CSSProperties}
          >
            <div>
              <div className="public-today-block-row" data-change={adjusted ? (block.change ?? undefined) : undefined}>
                <span className="public-today-block-glyph" aria-hidden="true">
                  {adjusted && block.change === "up" ? "↑" : adjusted && block.change === "down" ? "↓" : "·"}
                </span>
                <span className="public-today-block-name">{block.name}</span>
                <span className="public-today-block-tag" aria-hidden={!adjusted}>
                  {block.tag}
                </span>
                <span key={block.sets} className="public-today-block-dose">
                  {block.sets} × {formatMinutes(block.minutes)}
                </span>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </article>
  );
}
