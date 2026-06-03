/**
 * Deterministic JSON serialization for value comparison / hashing.
 *
 * `JSON.stringify` preserves insertion order of object keys, so two logically
 * identical payloads built with keys in a different order produce different
 * strings. `stableStringify` recursively sorts object keys (array order is left
 * intact, since order is meaningful there) so the same logical value always
 * serializes to the same string. Use it whenever a serialized form is compared
 * for equality — e.g. detecting whether an intake payload has changed.
 */
export function stableStringify(value: unknown): string {
  return JSON.stringify(sortValue(value));
}

function sortValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sortValue);
  }
  if (value && typeof value === "object") {
    // Defer to JSON.stringify for anything that isn't a plain object: values
    // with a toJSON() hook (e.g. Date) own their serialization, and class
    // instances shouldn't have their internals reordered key-by-key. Walking
    // only plain objects keeps key sorting safe and predictable.
    if (typeof (value as { toJSON?: unknown }).toJSON === "function") {
      return value;
    }
    if (Object.getPrototypeOf(value) !== Object.prototype) {
      return value;
    }
    const source = value as Record<string, unknown>;
    return Object.keys(source)
      .sort()
      .reduce<Record<string, unknown>>((acc, key) => {
        acc[key] = sortValue(source[key]);
        return acc;
      }, {});
  }
  return value;
}
