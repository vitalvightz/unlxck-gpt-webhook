"use client";

import type { CSSProperties } from "react";

interface SkeletonProps {
  variant?: "block" | "text" | "circle";
  width?: number | string;
  height?: number | string;
  className?: string;
  style?: CSSProperties;
}

export function Skeleton({
  variant = "block",
  width,
  height,
  className,
  style,
}: SkeletonProps) {
  const inlineStyle: CSSProperties = { ...style };
  if (width !== undefined) inlineStyle.width = typeof width === "number" ? `${width}px` : width;
  if (height !== undefined) inlineStyle.height = typeof height === "number" ? `${height}px` : height;
  const classes = ["skeleton", `skeleton-${variant}`, className].filter(Boolean).join(" ");
  return <span className={classes} style={inlineStyle} aria-hidden="true" />;
}

export function PlansFeaturedSkeleton() {
  return (
    <article className="list-card plan-card plans-featured-card plans-placeholder-card athlete-motion-slot athlete-motion-main" aria-busy="true">
      <div className="plans-featured-topline">
        <div className="plans-featured-kicker" style={{ display: "grid", gap: 8 }}>
          <Skeleton variant="text" width={140} height={11} />
          <Skeleton variant="text" width={220} height={13} />
        </div>
        <Skeleton variant="block" width={92} height={28} style={{ borderRadius: 999 }} />
      </div>
      <div className="plans-featured-main">
        <div className="plans-featured-copy" style={{ display: "grid", gap: 12 }}>
          <Skeleton variant="text" width={90} height={11} />
          <Skeleton variant="text" width={180} height={22} />
          <Skeleton variant="text" width="62%" height={28} />
          <Skeleton variant="text" width="80%" height={14} />
          <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
            <Skeleton variant="block" width={120} height={40} style={{ borderRadius: 12 }} />
            <Skeleton variant="block" width={92} height={40} style={{ borderRadius: 12 }} />
            <Skeleton variant="block" width={92} height={40} style={{ borderRadius: 12 }} />
          </div>
        </div>
        <div className="plans-featured-meta">
          <Skeleton variant="block" width="100%" height={56} style={{ borderRadius: 14 }} />
          <Skeleton variant="block" width="100%" height={56} style={{ borderRadius: 14 }} />
          <Skeleton variant="block" width="100%" height={56} style={{ borderRadius: 14 }} />
        </div>
      </div>
    </article>
  );
}

export function PlanHistoryRowSkeleton() {
  return (
    <article className="plan-history-row plan-history-row-card" aria-busy="true">
      <div className="plan-history-copy" style={{ display: "grid", gap: 8 }}>
        <Skeleton variant="text" width={120} height={11} />
        <Skeleton variant="text" width="55%" height={20} />
        <div style={{ display: "flex", gap: 12 }}>
          <Skeleton variant="text" width={120} height={12} />
          <Skeleton variant="text" width={140} height={12} />
        </div>
      </div>
      <div className="plan-history-meta" style={{ display: "grid", gap: 10, justifyItems: "end" }}>
        <Skeleton variant="block" width={92} height={24} style={{ borderRadius: 999 }} />
        <div style={{ display: "flex", gap: 8 }}>
          <Skeleton variant="block" width={88} height={36} style={{ borderRadius: 10 }} />
          <Skeleton variant="block" width={88} height={36} style={{ borderRadius: 10 }} />
        </div>
      </div>
    </article>
  );
}

export function NutritionWorkspaceSkeleton() {
  return (
    <section className="nutrition-page-grid" aria-busy="true">
      <div className="nutrition-main-column">
        {[0, 1, 2].map((index) => (
          <div className="nutrition-group" key={index}>
            <Skeleton variant="text" width={160} height={11} />
            <article className="step-card nutrition-section" style={{ display: "grid", gap: 16 }}>
              <Skeleton variant="text" width="42%" height={20} />
              <Skeleton variant="text" width="80%" height={14} />
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 }}>
                <Skeleton variant="block" height={64} style={{ borderRadius: 14 }} />
                <Skeleton variant="block" height={64} style={{ borderRadius: 14 }} />
                <Skeleton variant="block" height={64} style={{ borderRadius: 14 }} />
                <Skeleton variant="block" height={64} style={{ borderRadius: 14 }} />
              </div>
            </article>
          </div>
        ))}
      </div>
    </section>
  );
}
