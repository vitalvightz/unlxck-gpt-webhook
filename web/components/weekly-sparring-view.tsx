"use client";

import { useEffect, useMemo, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import { fetchWeeklySchedule } from "@/lib/api";
import type { SparringDayClass, WeeklyDayEntry, WeeklySchedule } from "@/lib/types";

const CLASS_LABELS: Record<SparringDayClass, string> = {
  primary_hard: "Primary hard",
  secondary_hard: "Secondary hard",
  managed_hard: "Managed hard",
  technical: "Technical / rhythm",
  none: "None",
};

const LOAD_LABELS: Record<WeeklyDayEntry["effective_load"], string> = {
  hard: "Hard",
  technical: "Technical",
  reduced: "Reduced",
  none: "None",
};

function formatToken(value: string) {
  const normalized = value.replace(/_/g, " ").trim();
  if (!normalized) {
    return "";
  }
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

export function WeeklySparringView({ planId }: { planId: string }) {
  const { session } = useAppSession();
  const token = session?.access_token ?? null;
  const [schedule, setSchedule] = useState<WeeklySchedule | null>(null);
  const [weekIndex, setWeekIndex] = useState(0);
  const [selectedWeekday, setSelectedWeekday] = useState<WeeklyDayEntry["weekday"] | null>(null);
  const [isHidden, setIsHidden] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setWeekIndex(0);
    setSelectedWeekday(null);
    setSchedule(null);
    setIsHidden(false);
    setError(null);
  }, [planId]);

  useEffect(() => {
    if (!token) {
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetchWeeklySchedule(planId, weekIndex, token)
      .then((nextSchedule) => {
        if (cancelled) {
          return;
        }
        setSchedule(nextSchedule);
        setIsHidden(nextSchedule === null);
        if (nextSchedule) {
          setSelectedWeekday((current) => {
            if (current && nextSchedule.days.some((day) => day.weekday === current)) {
              return current;
            }
            return null;
          });
        }
      })
      .catch((scheduleError) => {
        if (cancelled) {
          return;
        }
        setSchedule(null);
        setIsHidden(false);
        setError(scheduleError instanceof Error ? scheduleError.message : "Unable to load weekly schedule.");
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [planId, token, weekIndex]);

  const selectedDay = useMemo(
    () => schedule?.days.find((day) => day.weekday === selectedWeekday) ?? null,
    [schedule, selectedWeekday],
  );

  if (isHidden || (!schedule && !error)) {
    return null;
  }

  if (error && !schedule) {
    return (
      <section className="weekly-sparring-view weekly-sparring-error" aria-label="Weekly sparring schedule">
        <div className="weekly-sparring-header">
          <div>
            <p className="kicker">Weekly View</p>
            <h3>Live sparring map</h3>
          </div>
        </div>
        <p className="muted">{error}</p>
      </section>
    );
  }

  if (!schedule) {
    return null;
  }

  const canGoPrevious = schedule.week_index > 0;
  const canGoNext = schedule.week_index + 1 < schedule.week_count;

  return (
    <section
      className={`weekly-sparring-view ${isLoading ? "weekly-sparring-view-loading" : ""}`}
      aria-label="Weekly sparring schedule"
    >
      <div className="weekly-sparring-header">
        <div>
          <p className="kicker">Weekly View</p>
          <h3>Live sparring map</h3>
          <p className="muted weekly-sparring-phase">
            {schedule.phase ? `${formatToken(schedule.phase)} | ` : ""}Week {schedule.week_index + 1} of{" "}
            {schedule.week_count}
          </p>
        </div>
        <div className="weekly-sparring-nav" aria-label="Week navigation">
          <button
            type="button"
            className="ghost-button weekly-sparring-nav-button"
            onClick={() => setWeekIndex((current) => Math.max(0, current - 1))}
            disabled={!canGoPrevious || isLoading}
            aria-label="Previous week"
            title="Previous week"
          >
            Prev
          </button>
          <span className="weekly-sparring-week-label">
            {schedule.week_index + 1}/{schedule.week_count}
          </span>
          <button
            type="button"
            className="ghost-button weekly-sparring-nav-button"
            onClick={() => setWeekIndex((current) => Math.min(schedule.week_count - 1, current + 1))}
            disabled={!canGoNext || isLoading}
            aria-label="Next week"
            title="Next week"
          >
            Next
          </button>
        </div>
      </div>

      <div className="weekly-sparring-grid" role="list">
        {schedule.days.map((day) => (
          <button
            key={day.weekday}
            type="button"
            role="listitem"
            className={`weekly-sparring-tile weekly-sparring-tile-${day.sparring_day_class} ${
              selectedDay?.weekday === day.weekday ? "weekly-sparring-tile-selected" : ""
            }`}
            onClick={() => setSelectedWeekday(day.weekday)}
            aria-pressed={selectedDay?.weekday === day.weekday}
            title={`${day.weekday}: ${CLASS_LABELS[day.sparring_day_class]}`}
          >
            <span className="weekly-sparring-weekday">{day.weekday}</span>
            <span className={`weekly-sparring-class-badge weekly-sparring-badge-${day.sparring_day_class}`}>
              {CLASS_LABELS[day.sparring_day_class]}
            </span>
          </button>
        ))}
      </div>

      {selectedDay ? (
        <div className="weekly-sparring-detail">
          <div className="weekly-sparring-detail-header">
            <div>
              <p className="kicker">{selectedDay.weekday}</p>
              <h4>{CLASS_LABELS[selectedDay.sparring_day_class]}</h4>
            </div>
            <span className={`weekly-sparring-class-badge weekly-sparring-badge-${selectedDay.sparring_day_class}`}>
              {LOAD_LABELS[selectedDay.effective_load]}
            </span>
          </div>
          <div className="weekly-sparring-detail-grid">
            <div>
              <p className="weekly-sparring-detail-label">Status</p>
              <p>{formatToken(selectedDay.status) || "No assigned sparring"}</p>
            </div>
            <div>
              <p className="weekly-sparring-detail-label">Effective load</p>
              <p>{LOAD_LABELS[selectedDay.effective_load]}</p>
            </div>
          </div>
          {selectedDay.reason ? <p className="weekly-sparring-detail-copy">{selectedDay.reason}</p> : null}
          {selectedDay.coach_note ? (
            <p className="weekly-sparring-coach-note">{selectedDay.coach_note}</p>
          ) : null}
          {selectedDay.reason_codes.length ? (
            <div className="weekly-sparring-reason-codes" aria-label="Reason codes">
              {selectedDay.reason_codes.map((code) => (
                <span key={code} className="badge status-badge-neutral">
                  {formatToken(code)}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
