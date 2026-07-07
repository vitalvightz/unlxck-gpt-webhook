alter table public.injury_flags
  add column if not exists latest_reported_status text not null default 'ongoing';

alter table public.injury_flags
  drop constraint if exists injury_flags_latest_reported_status_check;

alter table public.injury_flags
  add constraint injury_flags_latest_reported_status_check
  check (latest_reported_status in ('ongoing', 'improving', 'worse', 'resolved'));
