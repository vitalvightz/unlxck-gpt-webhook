-- The original XP ledger migration left two legacy checks in place after the
-- expanded action and calendar-scope constraints were added. Those stale checks
-- reject every non-login award even though the newer constraints allow it.

alter table public.xp_awards
  drop constraint if exists xp_awards_check;

alter table public.xp_awards
  drop constraint if exists xp_awards_daily_calendar_required;
