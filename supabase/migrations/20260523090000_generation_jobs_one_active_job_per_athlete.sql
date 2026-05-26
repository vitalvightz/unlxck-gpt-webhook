with active_rows as (
    select
        id,
        athlete_id,
        row_number() over (
            partition by athlete_id
            order by created_at desc, id desc
        ) as rn
    from generation_jobs
    where status in ('queued', 'running')
)
update generation_jobs gj
set
    status = 'failed',
    error = coalesce(gj.error, 'Superseded by active-job uniqueness migration cleanup.'),
    completed_at = coalesce(gj.completed_at, now()),
    heartbeat_at = coalesce(gj.heartbeat_at, now())
from active_rows ar
where gj.id = ar.id
  and ar.rn > 1;

create unique index if not exists generation_jobs_one_active_job_per_athlete
on generation_jobs (athlete_id)
where status in ('queued', 'running');
