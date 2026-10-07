/** Freeze the document behind a viewport overlay, including iOS Safari.
 * Overflow alone allows a scrolled page to move behind a fixed dialog on iOS.
 * Nested overlays share the lock and restore the original scroll position. */
let locks = 0;
let restore: (() => void) | null = null;

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
  let released = false;
  return () => {
    if (released) return;
    released = true;
    if (--locks === 0) {
      restore?.();
      restore = null;
    }
  };
}
