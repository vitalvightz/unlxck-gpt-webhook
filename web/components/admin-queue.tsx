"use client";

import { Children, useState, type ReactNode } from "react";

export function AdminQueue({ header, children, className = "" }: {
  header: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <details className={`list-card admin-queue ${className}`} name="admin-queues">
      <summary>{header}<span className="admin-queue-toggle" aria-hidden="true">+</span></summary>
      <div className="admin-queue-content">{children}</div>
    </details>
  );
}

const PAGE_SIZE = 5;

export function AdminQueueList({ children, className, label }: {
  children: ReactNode;
  className: string;
  label: string;
}) {
  const items = Children.toArray(children);
  const [page, setPage] = useState(0);
  const lastPage = Math.max(0, Math.ceil(items.length / PAGE_SIZE) - 1);
  const currentPage = Math.min(page, lastPage);
  const start = currentPage * PAGE_SIZE;
  return (
    <>
      <div className={className}>{items.slice(start, start + PAGE_SIZE)}</div>
      {items.length > PAGE_SIZE ? (
        <nav className="admin-pager" aria-label={`${label} pagination`}>
          <button type="button" className="ghost-button" disabled={currentPage === 0}
            onClick={() => setPage(currentPage - 1)}>Previous</button>
          <span className="muted">{start + 1}–{Math.min(start + PAGE_SIZE, items.length)} of {items.length}</span>
          <button type="button" className="ghost-button" disabled={currentPage === lastPage}
            onClick={() => setPage(currentPage + 1)}>Next</button>
        </nav>
      ) : null}
    </>
  );
}
