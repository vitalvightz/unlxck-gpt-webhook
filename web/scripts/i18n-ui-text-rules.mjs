// What counts as user-facing UI copy, for the extractor and the coverage test.
//
// The first extraction pass only reached JSX text, a fixed list of JSX attributes and
// string literals inside a JSX conditional. Copy also lives in three other positions,
// and all three shipped as English on every locale:
//
//   const label = value || "Not set";                 // fallback operand
//   const status = done ? "Complete" : "In progress"; // conditional outside JSX
//   setError("Unable to save draft.");                // a UI sink
//
// Those are safe to extract because each one is a whole string. Template literals are
// deliberately NOT here: their spans are sentence fragments around an interpolation, and
// translating a fragment fixes English word order into every other language. Converting
// one needs an ICU message per site (and an ICU plural wherever the `n === 1 ? "" : "s"`
// idiom appears), which is per-site work rather than extraction.
//
// The rules below are deliberately conservative. Everything they cannot recognise as copy
// is left alone, because a wrongly extracted machine value is a runtime defect (a lookup
// key or a CSS class replaced by a translation) while a missed string is only untranslated.

// Only two positions are extracted automatically, and both are terminal — the string
// reaches a person and nothing else reads it back:
//
//   setError("Unable to save draft.")        // a UI sink, directly or through a ?: / ||
//   <p>{ready ? "Complete" : "Pending"}</p>  // rendered in place
//
// A literal assigned to a variable is deliberately NOT extracted, however much it looks
// like copy. `cleanText(block.display_name) || "Block"` in structured-plan-renderer.tsx is
// the reason: that value is rendered AND passed to a prescription lookup, so replacing it
// with a translation would silently break the lookup on every non-English locale. Those
// sites are localised at the point they are rendered, with translateUiText(), which keeps
// the English value in the code path that compares it.
/** Positions whose string literal is a whole piece of UI copy and reaches nothing else. */
export const TERMINAL_POSITIONS = ["ui-sink-argument", "jsx-rendered"];

/**
 * Functions whose string argument is shown to the athlete or the admin.
 *
 * Anything that reports to a person: the error/message/banner state setters the screens
 * render, and the toast helpers. Kept as an allowlist rather than a denylist, so a new
 * helper has to be named here before its arguments are treated as copy.
 */
export const UI_SINK_CALLEE = /^(?:set[A-Za-z]*(?:Error|Message|Banner|Notice|Warning)|showToast|toast|notify)$/;

/**
 * Callees whose string argument is never copy even though the name can look like it:
 * the translation hooks themselves (the argument is a namespace) and the lookup helpers.
 */
export const NON_UI_CALLEE = /^(?:useTranslations|useAppTranslations|getTranslations|appText|t)$/;

const NOT_COPY = [
  // A route, an href, an anchor or a mail link.
  /^(?:https?:\/\/|mailto:|\/[\w/[\]().-]*$|#[\w-]*$)/,
  // A machine value: an enum member, a storage key, a query key, a CSS class.
  /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/,
  // An identifier, including the `someId-` prefixes used to build DOM ids.
  /^[a-z][A-Za-z0-9]*-?$/,
  /^[A-Z][A-Z0-9_]+$/,
  // A class list: lowercase words joined by hyphens and spaces.
  /^[a-z0-9 _-]*-[a-z0-9 _-]*$/,
  // A date or number format pattern.
  /^[yMdHhmsAaZz\d\s:/.,'+-]+$/,
  // Content types, encodings and auth schemes.
  /^(?:application|text|image|audio|video|multipart)\//,
  /charset=|^(?:Bearer|Basic|utf-8|UTF-8)$/,
  // A key builder: `outcome${index}Label` leaves "outcome" and "Label" as spans.
  /^(?:Label|Value|Title|Body|Text)$/,
  // A cookie or header attribute: `...; Secure`, `; HttpOnly`. Copy never opens with one.
  /^[;,]\s*[A-Za-z][\w-]*$/,
];

/**
 * Whether a static string is user-facing UI copy.
 *
 * Copy reads as language: it is a sentence, a phrase, or a capitalised label. A single
 * lowercase token is a value, not copy.
 */
export function isTranslatableUiText(value) {
  const text = String(value ?? "").trim();
  if (text.length < 2) return false;
  // Needs letters, and at least two of them, so "%" or "x" never qualifies.
  if (!/\p{L}\p{L}/u.test(text)) return false;
  if (NOT_COPY.some((pattern) => pattern.test(text))) return false;
  // A leading capital (a label) or whitespace (a phrase). Both mean prose.
  return /^\p{Lu}/u.test(text) || /\s/.test(text);
}
