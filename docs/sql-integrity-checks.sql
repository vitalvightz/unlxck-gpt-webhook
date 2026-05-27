-- Terminal generation jobs that have no linked plan_id.
select
  id,
  athlete_id,
  status,
  source,
  plan_id,
  intake_id,
  completed_at
from generation_jobs
where status in ('completed', 'review_required')
  and (plan_id is null or trim(plan_id::text) = '');

-- Terminal generation jobs linked to a deleted/missing plan row.
select
  gj.id as generation_job_id,
  gj.athlete_id,
  gj.status as generation_status,
  gj.source,
  gj.plan_id,
  gj.completed_at
from generation_jobs gj
left join plans p on p.id::text = gj.plan_id::text
where gj.status in ('completed', 'review_required')
  and gj.plan_id is not null
  and trim(gj.plan_id::text) <> ''
  and p.id is null;

-- Plans carrying triage resume approval marker while latest linked admin resume job failed.
with latest_resume_job as (
  select distinct on (gj.plan_id)
    gj.plan_id,
    gj.id,
    gj.status,
    gj.error,
    gj.updated_at
  from generation_jobs gj
  where lower(coalesce(gj.source, '')) = 'admin_triage_resume'
    and gj.plan_id is not null
  order by gj.plan_id, gj.updated_at desc nulls last, gj.created_at desc nulls last
)
select
  p.id as plan_id,
  p.athlete_id,
  p.status as plan_status,
  p.stage2_status,
  lrj.id as latest_resume_job_id,
  lrj.status as latest_resume_job_status,
  lrj.error as latest_resume_job_error,
  lrj.updated_at as latest_resume_job_updated_at
from plans p
left join latest_resume_job lrj on lrj.plan_id::text = p.id::text
where lower(coalesce(p.stage2_status, '')) = 'triage_resume_approved'
  and (lrj.id is null or lrj.status = 'failed');
