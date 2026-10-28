"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Tracks whether an element is in the viewport. Returns a callback ref (so it
 * works on elements that mount after the hook runs) and the current state:
 * null until the first observation, then true/false. With `once`, it latches
 * true the first time the element is seen. Where IntersectionObserver is
 * unavailable the element counts as visible.
 */
export function useInView<T extends Element>({
  threshold = 0,
  once = false,
}: { threshold?: number; once?: boolean } = {}): [(node: T | null) => void, boolean | null] {
  const [node, setNode] = useState<T | null>(null);
  const [inView, setInView] = useState<boolean | null>(null);
  const ref = useCallback((next: T | null) => setNode(next), []);

  useEffect(() => {
    if (!node || (once && inView === true)) return;
    if (typeof IntersectionObserver === "undefined") {
      const frame = requestAnimationFrame(() => setInView(true));
      return () => cancelAnimationFrame(frame);
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        setInView(entry.isIntersecting);
        if (once && entry.isIntersecting) observer.disconnect();
      },
      { threshold },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [node, once, inView, threshold]);

  return [ref, inView];
}
