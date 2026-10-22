/** Freeze the document behind a viewport overlay, including iOS Safari.
 * Overflow alone allows a scrolled page to move behind a fixed dialog on iOS.
 * Nested overlays share the lock and restore the original scroll position. */
let locks = 0;
let restore: (() => void) | null = null;
// Bumped when an orphaned lock is force-cleared, so a late release from a
// holder of the cleared lock cannot drive the count below zero.
let generation = 0;

export function lockOverlayScroll(): () => void {
  if (locks++ === 0) {
    const body = document.body;
    const keys = ["position", "top", "left", "width", "overflow"] as const;
    const previous = keys.map((key) => body.style[key]);
    const x = window.scrollX;
    const y = window.scrollY;
    body.style.position = "fixed";
    body.style.top = `${-y}px`;
    body.style.left = `${-x}px`;
    body.style.width = "100%";
    body.style.overflow = "hidden";
    restore = () => {
      keys.forEach((key, index) => { body.style[key] = previous[index]; });
      window.scrollTo(x, y);
    };
  }
  const lockGeneration = generation;
  let released = false;
  return () => {
    if (released || lockGeneration !== generation) return;
    released = true;
    if (--locks === 0) {
      restore?.();
      restore = null;
    }
  };
}

// Everything that legitimately holds the lock while it is on screen.
const OPEN_OVERLAY_SELECTOR =
  'dialog[open], [aria-modal="true"], .custom-select-sheet-backdrop, html[data-mobile-nav-lock="true"]';

/** Clear a lock whose overlay is gone. A holder that never released (an
 * interrupted close, an iOS page restored from the back/forward cache) left
 * the body position:fixed, so the page could not scroll and iOS drew a dead
 * band under the tab bar. Called on navigation and page restore; a no-op
 * while any overlay is still open. */
export function releaseOrphanedOverlayScroll(): void {
  if (locks === 0 || document.querySelector(OPEN_OVERLAY_SELECTOR)) return;
  locks = 0;
  generation += 1;
  const release = restore;
  restore = null;
  release?.();
}
