"use client";

import { useEffect, useMemo, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import { WhyTooltip } from "@/components/why-tooltip";
import { fetchWeeklySchedule } from "@/lib/api";
import {
  explainEffectiveLoad,
  explainReasonCode,
  explainSparringClass,
} from "@/lib/sparring-reason-codes";
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
const WEEKDAY_ORDER: WeeklyDayEntry["weekday"][] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const WEEKDAY_FULL: Record<WeeklyDayEntry["weekday"], string> = {
  Mon: "Monday",
  Tue: "Tuesday",
  Wed: "Wednesday",
  Thu: "Thursday",
  Fri: "Friday",
  Sat: "Saturday",
  Sun: "Sunday",
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
  const datedDays = schedule.days.filter((day) => (day.calendar_date ?? "").trim().length > 0);
  if (datedDays.length > 0) {
    const first = datedDays[0]?.calendar_date?.trim();
    const last = datedDays[datedDays.length - 1]?.calendar_date?.trim();
    if (first && last) {
      const firstDate = new Date(first);
      const lastDate = new Date(last);
      if (!Number.isNaN(firstDate.getTime()) && !Number.isNaN(lastDate.getTime())) {
        const firstLabel = `${firstDate.getUTCDate()} ${firstDate.toLocaleString("en-GB", { month: "short", timeZone: "UTC" })}`;
        const lastLabel = `${lastDate.getUTCDate()} ${lastDate.toLocaleString("en-GB", { month: "short", timeZone: "UTC" })}`;
        return `${firstLabel} → ${lastLabel}`;
      }
    }
  }
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
  const weekday = day.weekday;
  const fullWeekday = WEEKDAY_FULL[weekday] ?? "Day";
  const rawCalendarDate = (day.calendar_date ?? "").trim();
  const rawDayLabel = (day.day_label ?? "").trim();
  if (!rawCalendarDate) {
    if (rawDayLabel) return `${fullWeekday} ${rawDayLabel}`;
    return (day.weekday_with_label ?? fullWeekday).trim() || fullWeekday;
  }

  const parsed = new Date(rawCalendarDate);
  if (Number.isNaN(parsed.getTime())) {
    return `${fullWeekday} ${rawCalendarDate}`.trim();
  }

  const dayOfMonth = parsed.getUTCDate();
  const monthName = parsed.toLocaleString("en-GB", { month: "long", timeZone: "UTC" });
  const lastDigit = dayOfMonth % 10;
  const suffix = dayOfMonth >= 11 && dayOfMonth <= 13 ? "th" : lastDigit === 1 ? "st" : lastDigit === 2 ? "nd" : lastDigit === 3 ? "rd" : "th";
  return `${fullWeekday} ${dayOfMonth}${suffix} ${monthName}`;
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
  const orderedDays = useMemo(() => {
    if (!schedule) return [];
    const byWeekday = new Map(schedule.days.map((day) => [day.weekday, day]));
    return WEEKDAY_ORDER.map((weekday) => byWeekday.get(weekday)).filter((day): day is WeeklyDayEntry => Boolean(day));
  }, [schedule]);
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
          <span className="weekly-sparring-week-label">{formatDayLabel(schedule)}</span>
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

      {hasHardSparringBan ? (
        <div className="weekly-sparring-ban-notice" role="status">
          All declared hard sparring from D-17 onward is technical/rhythm only. No effective hard sparring allowed.
        </div>
      ) : null}

      <div className="weekly-sparring-grid" role="list">
        {orderedDays.map((day) => (
          <button
            key={day.weekday}
            type="button"
            role="listitem"
            className={`weekly-sparring-tile weekly-sparring-tile-${day.sparring_day_class} ${
              day.is_fight_day ? "weekly-sparring-tile-fight-day" : ""
            } ${
              selectedDay?.weekday === day.weekday ? "weekly-sparring-tile-selected" : ""
            }`}
            onClick={() => setSelectedWeekday(day.weekday)}
            aria-pressed={selectedDay?.weekday === day.weekday}
            title={`${formatWeekdayLabel(day)}: ${CLASS_LABELS[day.sparring_day_class]}`}
          >
            <span className="weekly-sparring-weekday">{formatWeekdayLabel(day)}</span>
            {day.is_fight_day ? <span className="weekly-sparring-fight-pill">FIGHT DATE</span> : null}
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
              <h4>
                {CLASS_LABELS[selectedDay.sparring_day_class]}
                <WhyTooltip
                  title={explainSparringClass(selectedDay.sparring_day_class).title}
                  body={explainSparringClass(selectedDay.sparring_day_class).body}
                />
              </h4>
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
              <p className="weekly-sparring-detail-label">
                Effective load
                <WhyTooltip
                  title={explainEffectiveLoad(selectedDay.effective_load).title}
                  body={explainEffectiveLoad(selectedDay.effective_load).body}
                />
              </p>
              <p>{LOAD_LABELS[selectedDay.effective_load]}</p>
            </div>
          </div>
          {selectedDay.reason ? <p className="weekly-sparring-detail-copy">{selectedDay.reason}</p> : null}
          {selectedDay.coach_note ? (
            <p className="weekly-sparring-coach-note">{selectedDay.coach_note}</p>
          ) : null}
          {selectedDay.reason_codes.length ? (
            <div className="weekly-sparring-reason-codes" aria-label="Reason codes">
              {selectedDay.reason_codes.map((code) => {
                const explanation = explainReasonCode(code);
                return (
                  <span key={code} className="badge status-badge-neutral">
                    {formatToken(code)}
                    <WhyTooltip title={explanation.title} body={explanation.body} />
                  </span>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
