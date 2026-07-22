/**
 * Scroll-driven sizing for the floating mobile "Menu" toggle.
 *
 * The toggle is `position: fixed`, so once the page scrolls it floats over
 * mid-page content. To stay out of the way it condenses to an icon-only square
 * once the page is scrolled at all — but it is never hidden or disabled: a
 * primary navigation control must stay tappable at every scroll position.
 *
 * The decision is kept as a pure function so it can be unit-tested directly:
 * mounting `AppNav` would drag in `next/navigation`, the auth provider, and
 * `window.matchMedia` (unimplemented in jsdom), none of which the rule depends
 * on. `AppNav`'s scroll effect is the thin glue that feeds `window.scrollY`
 * samples through here.
 */

/** At or below this offset the toggle is shown at full size; past it the toggle
 *  condenses to an icon-only square so it covers as little content as possible.
 *  A small threshold (not 0) avoids flicker from momentum/rubber-band scrolling
 *  right at the top. */
export const NAV_TOGGLE_CONDENSE_THRESHOLD = 24;

/** Whether the toggle should render condensed (icon-only) at this scroll offset. */
export function isNavToggleCondensed(scrollY: number): boolean {
  return scrollY > NAV_TOGGLE_CONDENSE_THRESHOLD;
}
