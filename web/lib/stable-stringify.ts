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
