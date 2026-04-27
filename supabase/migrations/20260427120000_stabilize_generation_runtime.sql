-- Runtime schema alignment for the async plan-generation API.
-- Safe to run more than once.

create extension if not exists pgcrypto;

alter table public.plans
  add column if not exists draft_plan_text text not null default '',
  add column if not exists final_plan_text text not null default '',
  add column if not exists planning_brief text,
  add column if not exists stage2_payload jsonb,
  add column if not exists stage2_handoff_text text not null default '',
  add column if not exists stage2_retry_text text not null default '',
  add column if not exists stage2_validator_report jsonb not null default '{}'::jsonb,
  add column if not exists stage2_status text not null default '',
  add column if not exists stage2_attempt_count integer not null default 0,
  add column if not exists parsing_metadata jsonb;

update public.plans
set
  draft_plan_text = coalesce(nullif(draft_plan_text, ''), plan_text, ''),
  final_plan_text = coalesce(nullif(final_plan_text, ''), plan_text, ''),
  stage2_validator_report = coalesce(stage2_validator_report, '{}'::jsonb),
  stage2_attempt_count = coalesce(stage2_attempt_count, 0),
  stage2_handoff_text = coalesce(stage2_handoff_text, ''),
  stage2_retry_text = coalesce(stage2_retry_text, ''),
  stage2_status = coalesce(stage2_status, '');

create table if not exists public.generation_jobs (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  client_request_id text not null,
  source text not null default 'self_serve',
  request_payload jsonb not null default '{}'::jsonb,
  status text not null default 'queued' check (status in ('queued', 'running', 'completed', 'review_required', 'failed')),
  attempt_count integer not null default 0,
  heartbeat_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  error text,
  intake_id uuid references public.athlete_intakes(id) on delete set null,
  stage1_result jsonb,
  final_result jsonb,
  plan_id uuid references public.plans(id) on delete set null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (athlete_id, client_request_id)
);

create index if not exists generation_jobs_athlete_created_idx
  on public.generation_jobs (athlete_id, created_at desc);

create index if not exists generation_jobs_status_created_idx
  on public.generation_jobs (status, created_at);

create index if not exists generation_jobs_status_heartbeat_idx
  on public.generation_jobs (status, heartbeat_at);

create or replace function public.set_generation_jobs_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists set_generation_jobs_updated_at on public.generation_jobs;
create trigger set_generation_jobs_updated_at
before update on public.generation_jobs
for each row
execute function public.set_generation_jobs_updated_at();
