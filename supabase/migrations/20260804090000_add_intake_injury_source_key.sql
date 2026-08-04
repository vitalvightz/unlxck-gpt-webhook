-- Stable identity for intake-seeded injury flags.
-- The unique constraint makes concurrent Today/Plan/background reads idempotent.
alter table public.injury_flags
  add column if not exists source_key text;

create unique index if not exists injury_flags_athlete_source_key_uidx
  on public.injury_flags (athlete_id, source_key)
  where source_key is not null;
