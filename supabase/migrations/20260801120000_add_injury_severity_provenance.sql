-- Provenance for an injury flag's severity, so a system-applied floor can be
-- released again.
--
-- The surface (skin) follow-up derives a severity FLOOR from the structured
-- wound answers: an infected or draining wound is at least severe. Without
-- recording that the value came from that floor, the raise is permanent — the
-- next check-in reads the stored "severe" as the athlete's own choice and can
-- only ever raise from there, so a wound that has since closed and gone clean
-- stays classed severe until it is resolved outright.
--
-- ``severity_source`` says who owns the current value, and ``manual_severity``
-- preserves the athlete's own severity underneath a system floor so releasing
-- the floor restores it rather than guessing. A NULL ``severity_source`` (every
-- existing row) reads as 'manual': legacy severities are never auto-lowered.

alter table public.injury_flags
  add column if not exists severity_source text,
  add column if not exists manual_severity text;

alter table public.injury_flags
  drop constraint if exists injury_flags_severity_source_check;
alter table public.injury_flags
  add constraint injury_flags_severity_source_check
  check (severity_source is null or severity_source in ('manual', 'surface_system'));

alter table public.injury_flags
  drop constraint if exists injury_flags_manual_severity_check;
alter table public.injury_flags
  add constraint injury_flags_manual_severity_check
  check (manual_severity is null or manual_severity in ('mild', 'moderate', 'severe'));

-- ``manual_severity`` only means anything while a system floor is in force;
-- outside that, ``severity`` is itself the athlete's value. Keeping the pair
-- consistent in the database stops a partial write from stranding a floor with
-- no recorded value to fall back to.
alter table public.injury_flags
  drop constraint if exists injury_flags_manual_severity_pairing_check;
alter table public.injury_flags
  add constraint injury_flags_manual_severity_pairing_check
  check (
    (severity_source = 'surface_system' and manual_severity is not null)
    or (severity_source is distinct from 'surface_system' and manual_severity is null)
  );
