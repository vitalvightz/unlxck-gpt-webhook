import assert from "node:assert/strict";
import test from "node:test";

import { parseXpProgressResponse } from "./xp-progress";

function response(overrides: Record<string, unknown> = {}) {
  return {
    state: {
      total_xp: 620,
      last_daily_login_date: null,
      recent_awards: [
        {
          id: "award-1",
          action: "planned_session_completed",
          amount: 50,
          awarded_at: "2026-08-03T15:00:00Z",
        },
      ],
    },
    opportunities: [
      {
        code: "complete_today_session",
        label: "Complete today's session",
        xp: 75,
        href: "/today",
        priority: 30,
      },
    ],
    current_week: {
      plan_id: "plan-1",
      week_id: "week-1",
      week_index: 0,
      phase_label: "GPP",
      start_date: "2026-08-03",
      end_date: "2026-08-09",
      completed_sessions: 2,
      planned_sessions: 3,
      remaining_sessions: 1,
      complete: false,
      week_xp_earned: false,
    },
    major_milestones: [
      {
        id: "milestone-1",
        plan_id: "plan-1",
        milestone_type: "phase_completed",
        phase_label: "GPP",
        completed_at: "2026-08-02T10:00:00Z",
        display_label: "GPP phase complete",
      },
    ],
    ...overrides,
  };
}

test("parses the full progress contract", () => {
  const parsed = parseXpProgressResponse(response());

  assert.equal(parsed.state.totalXp, 620);
  assert.equal(parsed.state.recentAwards[0]?.action, "planned_session_completed");
  assert.equal(parsed.opportunities[0]?.xp, 75);
  assert.equal(parsed.currentWeek?.plannedSessions, 3);
  assert.equal(parsed.currentWeek?.remainingSessions, 1);
  assert.equal(parsed.majorMilestones[0]?.displayLabel, "GPP phase complete");
});

test("rejects more than three opportunity rows", () => {
  const opportunity = {
    code: "code",
    label: "Label",
    xp: 10,
    href: "/today",
    priority: 1,
  };
  assert.throws(
    () =>
      parseXpProgressResponse(
        response({
          opportunities: [
            { ...opportunity, code: "one" },
            { ...opportunity, code: "two" },
            { ...opportunity, code: "three" },
            { ...opportunity, code: "four" },
          ],
        }),
      ),
    /invalid XP progress/i,
  );
});

test("rejects inconsistent weekly counts", () => {
  assert.throws(
    () =>
      parseXpProgressResponse(
        response({
          current_week: {
            plan_id: "plan-1",
            week_id: "week-1",
            week_index: 0,
            phase_label: "GPP",
            start_date: "2026-08-03",
            end_date: "2026-08-09",
            completed_sessions: 2,
            planned_sessions: 3,
            remaining_sessions: 2,
            complete: false,
            week_xp_earned: false,
          },
        }),
      ),
    /invalid XP week progress/i,
  );
});

test("rejects an award whose amount disagrees with the action contract", () => {
  assert.throws(
    () =>
      parseXpProgressResponse(
        response({
          state: {
            total_xp: 620,
            last_daily_login_date: null,
            recent_awards: [
              {
                id: "award-1",
                action: "planned_session_completed",
                amount: 75,
                awarded_at: "2026-08-03T15:00:00Z",
              },
            ],
          },
        }),
      ),
    /invalid XP progress/i,
  );
});
