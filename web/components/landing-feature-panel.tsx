"use client";

import type { ReactNode } from "react";

import { useInView } from "@/lib/use-in-view";

export type LandingFeature = { title: string; body: string; icon: ReactNode };

/**
 * A landing panel of three icon-and-text rows under a kicker and heading.
 * Each panel tracks its own visibility so its icons draw in once, when that
 * list is first seen.
 */
export function LandingFeaturePanel({
  id,
  kicker,
  title,
  items,
}: Readonly<{ id: string; kicker: string; title: string; items: LandingFeature[] }>) {
  const [listRef, seen] = useInView<HTMLUListElement>({ threshold: 0.4, once: true });
  const headingId = `${id}-heading`;

  return (
    <section className="public-flex public-reveal" aria-labelledby={headingId}>
      <div className="public-section-head">
        <p className="kicker">{kicker}</p>
        <h2 id={headingId}>{title}</h2>
      </div>
      <ul ref={listRef} className="public-flex-list" data-seen={seen === true}>
        {items.map((item) => (
          <li key={item.title} className="public-flex-item">
            <span className="public-flex-icon" aria-hidden="true">
              {item.icon}
            </span>
            <div className="public-flex-copy">
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
