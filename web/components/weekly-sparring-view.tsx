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
  technical: "Technical / rhythm",
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

function formatDayLabel(schedule: WeeklySchedule) {
  const countdown = (schedule.week_countdown_label ?? "").trim();
  if (countdown) return countdown;
  const explicit = (schedule.day_label ?? "").trim();
  if (explicit) return explicit;
  const end = schedule.projected_days_until_fight_end;
  const start = schedule.projected_days_until_fight_start;
  if (typeof end === "number" && Number.isFinite(end) && end >= 0) {
    if (typeof start === "number" && Number.isFinite(start) && start > end) {
      return `D-${start} → D-${end}`;
    }
    return `D-${end}`;
  }
  return `block ${schedule.week_index + 1}/${schedule.week_count}`;
}

function formatWeekdayLabel(day: WeeklyDayEntry) {
  const labelled = (day.weekday_with_label ?? "").trim();
  if (labelled) return labelled;
  const dLabel = (day.day_label ?? "").trim();
  return dLabel ? `${day.weekday} (${dLabel})` : day.weekday;
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
  const hasHardSparringBan = schedule?.days.some((day) => day.reason_codes.includes("d17_hard_sparring_ban")) ?? false;

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
          <p className="kicker">Camp View</p>
          <h3>Live sparring map</h3>
          <p className="muted weekly-sparring-phase">{schedule.phase ? `${formatToken(schedule.phase)} | ` : ""}{formatDayLabel(schedule)}</p>
        </div>
        <div className="weekly-sparring-nav" aria-label="Camp navigation">
          <button
            type="button"
            className="ghost-button weekly-sparring-nav-button"
            onClick={() => setWeekIndex((current) => Math.max(0, current - 1))}
            disabled={!canGoPrevious || isLoading}
            aria-label="Previous day block"
            title="Previous day block"
          >
            Prev
          </button>
          <span className="weekly-sparring-week-label">{formatDayLabel(schedule)}</span>
          <button
            type="button"
            className="ghost-button weekly-sparring-nav-button"
            onClick={() => setWeekIndex((current) => Math.min(schedule.week_count - 1, current + 1))}
            disabled={!canGoNext || isLoading}
            aria-label="Next day block"
            title="Next day block"
          >
            Next
          </button>
        </div>
      </div>

      {hasHardSparringBan ? (
        <div className="weekly-sparring-ban-notice" role="status">
          All declared hard sparring from D-17 onward is technical/rhythm only. No effective hard sparring allowed.
        </div>
      ) : null}

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
            title={`${formatWeekdayLabel(day)}: ${CLASS_LABELS[day.sparring_day_class]}`}
          >
            <span className="weekly-sparring-weekday">{formatWeekdayLabel(day)}</span>
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
              <p className="kicker">{formatWeekdayLabel(selectedDay)}</p>
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
