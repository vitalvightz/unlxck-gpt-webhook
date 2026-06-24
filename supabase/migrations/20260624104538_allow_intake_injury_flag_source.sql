alter table public.injury_flags
  drop constraint if exists injury_flags_source_check;

alter table public.injury_flags
  add constraint injury_flags_source_check
  check (source in ('checkin', 'session_log', 'manual', 'admin', 'intake'));
