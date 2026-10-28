"use client";

import { useEffect, useState } from "react";

// Glyphs a character cycles through before it "unlocks" into place. ASCII
// only, so the mono font never falls back and the line keeps its width.
const SCRAMBLE_GLYPHS = "#%&*+=?/\\<>|01X@$";
const FRAME_MS = 45;

/**
 * The text with every character before `progress` (0..1) resolved and the
 * rest swapped for a random glyph. Spaces stay put so the line keeps its shape.
 */
export function scrambleText(text: string, progress: number, random: () => number = Math.random): string {
  const resolved = Math.floor(Math.max(0, Math.min(1, progress)) * text.length);
  return Array.from(text, (char, index) => {
    if (index < resolved || char === " ") return char;
    return SCRAMBLE_GLYPHS[Math.floor(random() * SCRAMBLE_GLYPHS.length)];
  }).join("");
}

type UnlockState = "locked" | "unlocking" | "unlocked";

/**
 * Decorative text that decodes from scrambled glyphs into `text`, left to
 * right, then settles. Hidden from assistive tech — render the real text
 * alongside it (e.g. in .sr-only). Under reduced motion it shows the text
 * straight away.
 */
export function UnlockGlitchText({
  text,
  className,
  delayMs = 0,
  durationMs = 900,
}: Readonly<{ text: string; className?: string; delayMs?: number; durationMs?: number }>) {
  // Reduced motion skips the decode entirely: the text starts unlocked.
  const [reduceMotion] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [display, setDisplay] = useState(() => (reduceMotion ? text : scrambleText(text, 0, () => 0)));
  const [state, setState] = useState<UnlockState>(reduceMotion ? "unlocked" : "locked");

  useEffect(() => {
    if (reduceMotion) return;
    const start = performance.now() + delayMs;
    const timer = window.setInterval(() => {
      const progress = (performance.now() - start) / durationMs;
      if (progress >= 1) {
        window.clearInterval(timer);
        setDisplay(text);
        setState("unlocked");
        return;
      }
      setDisplay(scrambleText(text, progress));
      setState(progress < 0 ? "locked" : "unlocking");
    }, FRAME_MS);
    return () => window.clearInterval(timer);
  }, [text, delayMs, durationMs, reduceMotion]);

  return (
    <span className={className ? `unlock-glitch ${className}` : "unlock-glitch"} data-text={display} data-state={state} aria-hidden="true">
      {display}
    </span>
  );
}
