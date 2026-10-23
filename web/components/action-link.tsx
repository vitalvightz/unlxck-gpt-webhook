import Link from "next/link";
import type { ComponentProps } from "react";

/** Quiet navigation beside a primary action; the full label remains a touch target. */
export function ActionLink({ children, className = "", ...props }: ComponentProps<typeof Link>) {
  return (
    <Link {...props} className={`action-link ${className}`.trim()}>
      <span>{children}</span>
      <svg className="action-link-arrow" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 12h14m-5-5 5 5-5 5" />
      </svg>
    </Link>
  );
}
