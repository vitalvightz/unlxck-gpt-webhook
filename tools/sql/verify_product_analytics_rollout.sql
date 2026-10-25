-- READ ONLY. Run after migration and deployment using the production admin
-- allowlist (same normalised emails as UNLXCK_ADMIN_EMAILS):
--   SET unlxck.analytics_admin_emails = '{}'; -- explicitly set the real array
-- A missing setting is an error; never silently verify a different population.
-- This verifier now also requires the corrective #3039 projection and checks
-- all-time plan maturity/conversion independently of the function's flags.
begin isolation level repeatable read read only;
with payload as (
 select public.product_analytics_facts(current_setting('unlxck.analytics_admin_emails')::text[]) as data
), athletes as (
 select (p->>'id')::uuid id from payload,jsonb_array_elements(data->'athletes') p
), expected as (
 select 'strength_starts' metric,count(*) total from public.session_completions c join athletes p on p.id=c.athlete_id where c.started_at is not null and c.started_at<=now()
 union all select 'strength_completions',count(*) from public.session_completions c join athletes p on p.id=c.athlete_id where c.status in ('done','modified') and c.completed_at is not null and c.completed_at<=now()
 union all select 'manual_completions',count(*) from public.external_training_sessions c join athletes p on p.id=c.athlete_id where c.deleted_at is null and c.created_at<=now()
 union all select 'sparring_logs',count(*) from public.sparring_logs c join athletes p on p.id=c.athlete_id where c.created_at<=now()
 union all select 'recovery_checkins', (select count(*) from public.today_checkins c join athletes p on p.id=c.athlete_id where c.created_at<=now())+(select count(*) from public.daily_checkins c join athletes p on p.id=c.athlete_id where c.created_at<=now())
 union all select 'usable_plans',count(*) from public.plans pl join athletes p on p.id=pl.athlete_id where pl.status in ('ready','publishable_with_flags') and pl.created_at<=now()
 union all select 'mature_usable_plans',count(*) from public.plans pl join athletes p on p.id=pl.athlete_id where pl.status in ('ready','publishable_with_flags') and pl.created_at+interval '7 days'<=now()
 union all select 'mature_trained_within_7d',count(*) from public.plans pl join athletes p on p.id=pl.athlete_id where pl.status in ('ready','publishable_with_flags') and pl.created_at+interval '7 days'<=now()
 and exists(select 1 from public.session_completions c where c.athlete_id=pl.athlete_id and c.plan_id=pl.id and c.status in ('done','modified') and c.completed_at>=pl.created_at and c.completed_at<pl.created_at+interval '7 days')
), facts as (
 select f->>'feature' feature,f->>'action' action,(f->>'count')::bigint total from payload,jsonb_array_elements(data->'facts') f
), measured as (
 select 'strength_starts' metric,coalesce(sum(total),0) total from facts where feature='strength' and action='session_started'
 union all select 'strength_completions',coalesce(sum(total),0) from facts where feature='strength' and action in ('session_completed','session_modified')
 union all select 'manual_completions',coalesce(sum(total),0) from facts where feature='manual' and action='session_completed'
 union all select 'sparring_logs',coalesce(sum(total),0) from facts where feature='sparring' and action='log_created'
 union all select 'recovery_checkins',coalesce(sum(total),0) from facts where feature='recovery' and action='checkin_completed'
 union all select 'usable_plans',count(*) from payload,jsonb_array_elements(data->'plans_used') pl where pl->>'status' in ('ready','publishable_with_flags')
 union all select 'mature_usable_plans',count(*) from payload,jsonb_array_elements(data->'plans_used') pl where pl->>'status' in ('ready','publishable_with_flags') and (pl->>'created_at')::timestamptz+interval '7 days'<=now()
 union all select 'mature_trained_within_7d',count(*) from payload,jsonb_array_elements(data->'plans_used') pl where pl->>'status' in ('ready','publishable_with_flags') and (pl->>'created_at')::timestamptz+interval '7 days'<=now() and (pl->>'completed_within_7d')::boolean
), checks as (
 select e.metric,e.total expected,m.total measured,e.total=m.total passed from expected e join measured m using(metric)
), health as (
 select public.product_analytics_retention_health() status
)
select jsonb_build_object('checked_at',now(),'population','same exclusions as deployed admin configuration',
 'source_checks',(select jsonb_agg(to_jsonb(c)) from checks c),
 'source_counts_match',(select bool_and(passed) from checks),
 'corrective_projection_available',(select data ?& array['optional_coverage','training_records','error_returns'] from payload),
 'retention',status,
 'first_scheduled_cleanup_verified',status->>'last_success_at' is not null,
 'release_verified',(select data ?& array['optional_coverage','training_records','error_returns'] from payload) and (select bool_and(passed) from checks) and (status->>'healthy')::boolean and status->>'last_success_at' is not null
) as verification from health;
commit;
