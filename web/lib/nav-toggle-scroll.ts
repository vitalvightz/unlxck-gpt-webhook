/**
 * Scroll-driven visibility logic for the floating mobile "Menu" toggle.
 *
 * The toggle is `position: fixed`, so once the page scrolls it floats over
 * mid-page content. To stay out of the way it hides while the athlete scrolls
 * down, returns on any scroll up (or near the top), and condenses to an
 * icon-only square once scrolled at all.
 *
 * The decision is kept as a pure function so it can be unit-tested directly:
 * mounting `AppNav` would drag in `next/navigation`, the auth provider, and
 * `window.matchMedia` (unimplemented in jsdom), none of which the scroll rule
 * depends on. `AppNav`'s scroll effect is the thin glue that feeds real
 * `window.scrollY` samples through here.
 */

export type NavToggleScrollState = {
  /** Slid off-screen (scrolling down, away from the top). */
  hidden: boolean;
  /** Shrunk to an icon-only square (any scroll past the top). */
  condensed: boolean;
};

export const NAV_TOGGLE_INITIAL_STATE: NavToggleScrollState = {
  hidden: false,
  condensed: false,
};

/** At or below this offset the toggle is always fully shown and un-condensed —
 *  it never covers content while the page sits at the top. */
export const NAV_TOGGLE_TOP_THRESHOLD = 24;

/** Only start hiding once scrolled past this offset, so a small nudge near the
 *  top never makes the toggle disappear. */
export const NAV_TOGGLE_HIDE_THRESHOLD = 90;

/**
 * Next visibility state for a scroll sample. Pure: same inputs → same output.
 *
 * @param current  the state before this sample (to preserve hidden across
 *                 samples with no vertical movement).
 * @param y        the current `scrollY`.
 * @param lastY    the previous `scrollY` (direction = sign of `y - lastY`).
 */
export function nextNavToggleScrollState(
  current: NavToggleScrollState,
  y: number,
  lastY: number,
): NavToggleScrollState {
  const condensed = y > NAV_TOGGLE_TOP_THRESHOLD;
  const delta = y - lastY;

  let hidden = current.hidden;
  if (y <= NAV_TOGGLE_TOP_THRESHOLD) {
    // Near the top: always visible.
    hidden = false;
  } else if (delta > 0 && y > NAV_TOGGLE_HIDE_THRESHOLD) {
    // Scrolling down, well past the top: get out of the way.
    hidden = true;
  } else if (delta < 0) {
    // Any scroll up brings it back immediately.
    hidden = false;
  }

  return { hidden, condensed };
}
