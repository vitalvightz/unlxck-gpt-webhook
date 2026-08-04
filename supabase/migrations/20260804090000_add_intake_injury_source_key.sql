-- Stable identity for intake-seeded injury flags.
-- NULL source keys remain unrestricted for manual/check-in rows, while intake
-- rows are protected from concurrent duplicate creation.
alter table public.injury_flags
  add column if not exists source_key text;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'injury_flags_athlete_source_key_key'
      and conrelid = 'public.injury_flags'::regclass
  ) then
    alter table public.injury_flags
      add constraint injury_flags_athlete_source_key_key
      unique (athlete_id, source_key);
  end if;
end
$$;
