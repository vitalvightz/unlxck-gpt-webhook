"use client";

import { useEffect, useState } from "react";

import { usePrefersReducedMotion } from "@/lib/reduced-motion";

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
 * straight away. The first `accentLength` characters get their own span
 * (.unlock-glitch-accent) so one phrase can carry a coloured lead word.
 */
export function UnlockGlitchText({
  text,
  className,
  delayMs = 0,
  durationMs = 900,
  accentLength = 0,
}: Readonly<{ text: string; className?: string; delayMs?: number; durationMs?: number; accentLength?: number }>) {
  const reduceMotion = usePrefersReducedMotion();
  const [display, setDisplay] = useState(() => scrambleText(text, 0, () => 0));
  const [state, setState] = useState<UnlockState>("locked");

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

  const shown = reduceMotion ? text : display;

  return (
    <span
      className={className ? `unlock-glitch ${className}` : "unlock-glitch"}
      data-text={shown}
      data-state={reduceMotion ? "unlocked" : state}
      aria-hidden="true"
    >
      {accentLength > 0 ? (
        <>
          <span className="unlock-glitch-accent">{shown.slice(0, accentLength)}</span>
          {shown.slice(accentLength)}
        </>
      ) : (
        shown
      )}
    </span>
  );
}
