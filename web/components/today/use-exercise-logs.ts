"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { ExerciseLogging } from "@/components/exercise-log";
import { listTodayExerciseLogs, submitExerciseLog } from "@/lib/api";
import type { ExerciseLogRecord } from "@/lib/types";

/**
 * Today's exercise logs for the active plan, and the save that writes one.
 * Returns null while logging is closed (no started session today), so the
 * exercise rows render without any log controls.
 */
export function useTodayExerciseLogs({
  token,
  planId,
  trainingDay,
  enabled,
  painReasonAllowed,
  onError,
}: {
  token: string;
  planId: string;
  /** The server's training day: a new day starts from an empty set of logs. */
  trainingDay: string;
  /** The server only accepts a log for a session started or completed today. */
  enabled: boolean;
  painReasonAllowed: boolean;
  /** Reports a failed one-tap save from a collapsed row. */
  onError?: (message: string) => void;
}): ExerciseLogging | null {
  const scope = `${planId}:${trainingDay}`;
  const [loaded, setLoaded] = useState<{ scope: string; logs: Record<string, ExerciseLogRecord> }>({
    scope,
    logs: {},
  });
  const active = enabled && Boolean(token) && Boolean(planId);

  useEffect(() => {
    if (!active) {
      return;
    }
    let cancelled = false;
    void listTodayExerciseLogs(token, planId)
      .then((response) => {
        if (cancelled) return;
        const fetched = Object.fromEntries(response.logs.map((log) => [log.block_id, log]));
        // A log saved while the list was loading is newer than the list.
        setLoaded((current) => ({
          scope,
          logs: current.scope === scope ? { ...fetched, ...current.logs } : fetched,
        }));
      })
      .catch((error: unknown) => {
        // The rows stay loggable; a save still returns the stored log.
        if (process.env.NODE_ENV !== "production") {
          console.error("Exercise logs could not be loaded", error);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [active, token, planId, scope]);

  const save = useCallback<ExerciseLogging["save"]>(
    async (request) => {
      const response = await submitExerciseLog(token, { plan_id: planId, ...request });
      setLoaded((current) => ({
        scope,
        logs: { ...(current.scope === scope ? current.logs : {}), [response.log.block_id]: response.log },
      }));
    },
    [token, planId, scope],
  );

  const logs = loaded.scope === scope ? loaded.logs : EMPTY_LOGS;
  return useMemo(
    () => (active ? { logs, save, painReasonAllowed, onError } : null),
    [active, logs, save, painReasonAllowed, onError],
  );
}

const EMPTY_LOGS: Record<string, ExerciseLogRecord> = {};
