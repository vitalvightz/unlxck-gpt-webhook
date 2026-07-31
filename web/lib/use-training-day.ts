"use client";

import { useEffect, useState } from "react";

import { resolveTrainingDay } from "@/lib/camp-map";

/**
 * The athlete-local training day (a Date at local midnight), resolved on the
 * client only. Returns `null` on the server and on the first client render so
 * SSR output and hydration match — date-dependent UI (current-day highlight,
 * today's blocks) renders its neutral "no current day" state until mount, then
 * fills in. Re-resolves every minute and on tab focus/visibility so a tab left
 * open across midnight / the 03:00 rollover advances to the new day instead of
 * sticking on the old one.
 */
export function useTrainingDay(): Date | null {
  const [trainingDay, setTrainingDay] = useState<Date | null>(null);

  useEffect(() => {
    const update = () => {
      const next = resolveTrainingDay(new Date());
      setTrainingDay((prev) =>
        prev && prev.getTime() === next.getTime() ? prev : next,
      );
    };

    update();
    const interval = window.setInterval(update, 60_000);
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        update();
      }
    };
    window.addEventListener("focus", update);
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", update);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return trainingDay;
}
