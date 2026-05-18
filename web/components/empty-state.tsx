import Link from "next/link";
import type { ReactNode } from "react";

type EmptyStateAction = {
  label: string;
  href: string;
};

type EmptyStateProps = {
  eyebrow?: string;
  title: string;
  description: string;
  example: string;
  primaryAction?: EmptyStateAction;
  secondaryAction?: EmptyStateAction;
  /** Optional override for the primary action when it is not a link (e.g. a button that focuses an input). */
  primaryActionNode?: ReactNode;
};

export function EmptyState({
  eyebrow,
  title,
  description,
  example,
  primaryAction,
  secondaryAction,
  primaryActionNode,
}: EmptyStateProps) {
  const hasActions = Boolean(primaryAction || primaryActionNode || secondaryAction);

  return (
    <div className="support-panel empty-state-card" role="status">
      <div className="empty-state-copy">
        {eyebrow ? <p className="kicker">{eyebrow}</p> : null}
        <h3 className="empty-state-title">{title}</h3>
        <p className="muted empty-state-description">{description}</p>
      </div>
      <div className="empty-state-example" aria-hidden="false">
        <p className="label">What appears here next</p>
        <p className="empty-state-example-body">{example}</p>
      </div>
      {hasActions ? (
        <div className="plan-card-actions empty-state-actions">
          {primaryActionNode ? (
            primaryActionNode
          ) : primaryAction ? (
            <Link href={primaryAction.href} className="cta">
              {primaryAction.label}
            </Link>
          ) : null}
          {secondaryAction ? (
            <Link href={secondaryAction.href} className="ghost-button">
              {secondaryAction.label}
            </Link>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
