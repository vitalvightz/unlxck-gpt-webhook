-- Adds a JSONB column for streaming semantic progress milestones during plan generation.
-- Each milestone is appended in order as { code, label, detail, at } so the loading
-- shell can render a coach-style timeline instead of just a phase chip.
-- Safe to run more than once.

alter table public.generation_jobs
  add column if not exists progress_milestones jsonb not null default '[]'::jsonb;

update public.generation_jobs
set progress_milestones = '[]'::jsonb
where progress_milestones is null;
