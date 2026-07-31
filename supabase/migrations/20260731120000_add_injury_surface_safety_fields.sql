-- Structured surface (skin) safety answers for injury_flags.
--
-- A blister, graze or abrasion is a hygiene/friction constraint, not a
-- musculoskeletal injury, so marking one "worse" must not stop all training.
-- Routing it safely needs structured facts instead of free text: is the skin
-- open, is it bleeding or draining, are there infection signs, can it stay
-- covered, and is rubbing/contact the actual problem.
--
-- Every column is nullable (or defaults to an empty list): existing rows and
-- existing clients stay valid, and a missing answer is read as "unknown",
-- never as "clear". Vocabulary matches the guided injury intake
-- (open_wound -> skin_integrity, bleeding_status, infection_signs).

alter table public.injury_flags
  add column if not exists skin_integrity text,
  add column if not exists bleeding_status text,
  add column if not exists drainage text,
  add column if not exists infection_signs jsonb not null default '[]'::jsonb,
  add column if not exists coverable text,
  add column if not exists friction_or_contact_problem text;

alter table public.injury_flags
  drop constraint if exists injury_flags_skin_integrity_check;
alter table public.injury_flags
  add constraint injury_flags_skin_integrity_check
  check (skin_integrity is null or skin_integrity in ('intact', 'open', 'unknown'));

alter table public.injury_flags
  drop constraint if exists injury_flags_bleeding_status_check;
alter table public.injury_flags
  add constraint injury_flags_bleeding_status_check
  check (bleeding_status is null or bleeding_status in ('none', 'controlled', 'uncontrolled'));

alter table public.injury_flags
  drop constraint if exists injury_flags_drainage_check;
alter table public.injury_flags
  add constraint injury_flags_drainage_check
  check (drainage is null or drainage in ('none', 'present', 'unknown'));

alter table public.injury_flags
  drop constraint if exists injury_flags_coverable_check;
alter table public.injury_flags
  add constraint injury_flags_coverable_check
  check (coverable is null or coverable in ('yes', 'no', 'unknown'));

alter table public.injury_flags
  drop constraint if exists injury_flags_friction_problem_check;
alter table public.injury_flags
  add constraint injury_flags_friction_problem_check
  check (
    friction_or_contact_problem is null
    or friction_or_contact_problem in ('yes', 'no', 'unknown')
  );

alter table public.injury_flags
  drop constraint if exists injury_flags_infection_signs_check;
alter table public.injury_flags
  add constraint injury_flags_infection_signs_check
  check (jsonb_typeof(infection_signs) = 'array' and jsonb_array_length(infection_signs) <= 8);
