-- Keep stored statuses aligned with api/state_machine.py.
-- Safe to run more than once.

update public.generation_jobs
set status = case
  when status is null or btrim(status) = '' then 'queued'
  when lower(btrim(status)) in ('queued', 'running', 'completed', 'review_required', 'failed') then lower(btrim(status))
  when lower(btrim(status)) in ('held_for_review', 'needs_review', 'medical_hold', 'restricted_rehab_only') then 'review_required'
  when lower(btrim(status)) in ('generated', 'ready', 'publishable_with_flags', 'triage_blocked', 'archived') then 'completed'
  else 'review_required'
end
where status is null
   or status <> lower(btrim(status))
   or lower(btrim(status)) not in ('queued', 'running', 'completed', 'review_required', 'failed');

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'generation_jobs_status_check'
      and conrelid = 'public.generation_jobs'::regclass
  ) then
    alter table public.generation_jobs
      add constraint generation_jobs_status_check
      check (status in ('queued', 'running', 'completed', 'review_required', 'failed'));
  end if;
end
$$;

update public.plans
set status = 'generated'
where status is null or btrim(status) = '';

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'plans_status_check'
      and conrelid = 'public.plans'::regclass
  ) then
    alter table public.plans
      add constraint plans_status_check
      check (
        status in (
          'generated',
          'ready',
          'review_required',
          'held_for_review',
          'publishable_with_flags',
          'triage_blocked',
          'medical_hold',
          'restricted_rehab_only',
          'needs_review',
          'archived'
        )
      )
      not valid;
  end if;
end
$$;
