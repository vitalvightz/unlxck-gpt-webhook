-- Harden XP uniqueness and calendar scope after the legacy-compatible award RPC
-- has already been installed by 20260803174400. Keeping this migration focused
-- means no intermediate migration prefix can reject the currently deployed
-- backend's three-parameter XP calls.

create unique index if not exists xp_awards_one_time_action_per_athlete
  on public.xp_awards (athlete_id, action)
  where action in (
    'profile_completed',
    'first_intake_completed',
    'first_plan_ready',
    'first_checkin_completed',
    'first_plan_completed'
  );

create unique index if not exists xp_awards_one_daily_action_per_athlete
  on public.xp_awards (athlete_id, action, calendar_date)
  where action in (
    'full_training_week_completed',
    'readiness_checkin_completed',
    'injury_update_completed',
    'stop_decision_followed'
  ) and calendar_date is not null;

alter table public.xp_awards
  drop constraint if exists xp_awards_calendar_scope_check;

alter table public.xp_awards
  add constraint xp_awards_calendar_scope_check check (
    (
      action in (
        'daily_login',
        'training_logged',
        'planned_session_completed',
        'full_training_week_completed',
        'readiness_checkin_completed',
        'injury_update_completed',
        'stop_decision_followed',
        'feedback_submitted',
        'feedback_with_comment'
      )
      and calendar_date is not null
    )
    or
    (
      action not in (
        'daily_login',
        'training_logged',
        'planned_session_completed',
        'full_training_week_completed',
        'readiness_checkin_completed',
        'injury_update_completed',
        'stop_decision_followed',
        'feedback_submitted',
        'feedback_with_comment'
      )
      and calendar_date is null
    )
  );
