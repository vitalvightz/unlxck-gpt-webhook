create or replace function public.validate_generation_job_active_lock()
returns boolean
language sql
stable
as $$
select exists (
  select 1
  from pg_indexes
  where schemaname = 'public'
    and tablename = 'generation_jobs'
    and indexname = 'generation_jobs_one_active_job_per_athlete'
    and lower(indexdef) like 'create unique index%'
    and lower(indexdef) like '%(athlete_id)%'
    and lower(indexdef) like '%where%'
    and lower(indexdef) like '%queued%'
    and lower(indexdef) like '%running%'
);
$$;
