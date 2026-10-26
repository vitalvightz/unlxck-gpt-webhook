"use client";

import {
  CALENDAR_WEEKDAYS,
  calendarCaption,
  type CalendarCellState,
  type CalendarRow,
} from "@/lib/plan-calendar";

const LEGEND: { state: CalendarCellState; label: string }[] = [
  { state: "done", label: "Done" },
  { state: "missed", label: "Missed" },
  { state: "planned", label: "Planned" },
  { state: "coach", label: "Coach/gym" },
];

/** Whole-block calendar: one row per week, Monday first. Tapping a training
 * day hands its plan week/day back so the list view can open it. */
export function PlanCalendar({
  rows,
  selectedWeekPos,
  onSelectDay,
}: {
  rows: CalendarRow[];
  selectedWeekPos: number;
  onSelectDay: (weekPos: number, dayIndex: number) => void;
}) {
  if (rows.length === 0) {
    return <p className="sp-muted">No days scheduled yet.</p>;
  }
  const caption = calendarCaption(rows);
  return (
    <section className="sp-card cm-calendar">
      <table className="cm-cal-table">
        <caption className={caption ? "cm-cal-caption" : "sr-only"}>{caption ?? "Plan calendar"}</caption>
        <thead>
          <tr>
            <th scope="col" className="cm-cal-week-head">
              <span className="sr-only">Week</span>
            </th>
            {CALENDAR_WEEKDAYS.map((weekday) => (
              <th key={weekday} scope="col" className="cm-cal-weekday">
                <abbr title={weekday}>{weekday.slice(0, 1)}</abbr>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.key}
              className={`cm-cal-row${row.weekPos !== null && row.weekPos === selectedWeekPos ? " cm-cal-row-selected" : ""}`}
            >
              <th scope="row" className="cm-cal-week">
                {row.label}
              </th>
              {row.cells.map((cell) => {
                const className = `cm-cal-cell${cell.isToday ? " cm-cal-today" : ""}`;
                const content = (
                  <>
                    <span className="cm-cal-num" aria-hidden="true">
                      {cell.dayNumber ?? ""}
                    </span>
                    <span className="cm-cal-dot" data-state={cell.state} aria-hidden="true" />
                    <span className="sr-only">
                      {cell.label}
                      {cell.isToday ? " (today)" : ""}
                    </span>
                  </>
                );
                const openable =
                  cell.weekPos !== null && cell.dayIndex !== null && cell.state !== "rest" && cell.state !== "outside";
                return (
                  <td key={cell.key} data-state={cell.state}>
                    {openable ? (
                      <button
                        type="button"
                        className={className}
                        onClick={() => onSelectDay(cell.weekPos as number, cell.dayIndex as number)}
                      >
                        {content}
                      </button>
                    ) : (
                      <span className={className}>{content}</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="cm-cal-legend" aria-label="Calendar key">
        {LEGEND.map((item) => (
          <li key={item.state}>
            <span className="cm-cal-dot" data-state={item.state} aria-hidden="true" />
            {item.label}
          </li>
        ))}
      </ul>
    </section>
  );
}
