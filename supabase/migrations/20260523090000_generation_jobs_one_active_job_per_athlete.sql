create unique index if not exists generation_jobs_one_active_job_per_athlete
on generation_jobs (athlete_id)
where status in ('queued', 'running');
