-- Deployment prerequisite: optional collection must never silently omit expiry.
do $$ begin
 if not exists(select 1 from pg_extension where extname='pg_cron') then
  raise exception 'Enable pg_cron before applying athlete product analytics; daily expiry is required';
 end if;
end $$;
-- Durable internal-account configuration. No profile FK: deleting/recreating
-- a profile must never remove its email exclusion. Service-role only.
create table public.product_analytics_excluded_emails (
 email text primary key check (email=lower(btrim(email)) and email<>'' and length(email)<=320)
);
alter table public.product_analytics_excluded_emails enable row level security;
revoke all on public.product_analytics_excluded_emails from anon,authenticated;
grant select,insert,update,delete on public.product_analytics_excluded_emails to service_role;
insert into public.product_analytics_excluded_emails(email) values
 ('vitalvightz@gmail.com'),('michaelokafor@gmail.com'),('michaelokafor@tutanota.com'),
 ('thevital1@tutanota.com'),('frankribery@mailfence.com'),('jjjjjjj@hotmail.com'),('vitalvightz@proton.me');

-- Only missing interactions; no payload, URLs, device IDs, notes or health data.
create table public.product_events (
 id uuid primary key default gen_random_uuid(),
 athlete_id uuid not null references public.profiles(id) on delete cascade,
 event_name text not null check (event_name in (
 'plan_opened','plan_editor_opened','plan_edited','plan_replaced',
 'timer_started','timer_round_completed','timer_completed','timer_exited',
 'history_opened','nutrition_opened','nutrition_saved','feedback_prompt_shown',
 'operation_failed','frontend_error')),
 feature text not null check (feature in ('plans','strength','timer','sparring','history','recovery','nutrition','manual','feedback','onboarding')),
 request_id uuid not null,
 flow_id uuid,
 created_at timestamptz not null default now(),
 unique(athlete_id, event_name, request_id)
);
alter table public.product_events enable row level security;
revoke all on public.product_events from anon, authenticated;
grant all on public.product_events to service_role;
create index product_events_athlete_time on public.product_events(athlete_id, created_at desc);
create index product_events_time_feature on public.product_events(created_at, feature, event_name);
-- Explicitly managed by admins; never inferred from an email naming convention.
alter table public.profiles add column analytics_excluded boolean not null default false;
alter table public.profiles add column onboarding_started_at timestamptz;
alter table public.profiles add column onboarding_completed_at timestamptz;
create function public.record_onboarding_stage(p_athlete_id uuid, p_completed boolean default false)
returns void language sql security invoker set search_path=public,pg_temp as $$
 update public.profiles set onboarding_started_at=coalesce(onboarding_started_at,now()),
 onboarding_completed_at=case when p_completed then coalesce(onboarding_completed_at,now()) else onboarding_completed_at end
 where id=p_athlete_id;
$$;
revoke all on function public.record_onboarding_stage(uuid,boolean) from public,anon,authenticated;
grant execute on function public.record_onboarding_stage(uuid,boolean) to service_role;
revoke update(analytics_excluded) on public.profiles from authenticated;

-- A private projection of existing evidence. Discovery and generation are not activity.
create view public.product_activity with (security_invoker=true) as
 select id::text || ':start' as id, athlete_id, started_at as occurred_at,
 'strength'::text as feature, 'session_started'::text as action, true as meaningful, plan_id::text as flow_id
 from public.session_completions where started_at is not null
 union all select id::text || ':complete', athlete_id, completed_at, 'strength',
 case when status='modified' then 'session_modified' else 'session_completed' end, true, plan_id::text
 from public.session_completions where status in ('done','modified') and completed_at is not null
 union all select id::text, athlete_id, created_at, 'manual', 'session_completed', true, null
 from public.external_training_sessions where deleted_at is null
 union all select id::text, athlete_id, created_at, 'sparring', 'log_created', true, null from public.sparring_logs
 union all select id::text, athlete_id, created_at, 'recovery', 'checkin_completed', true, null from public.today_checkins
 union all select id::text, athlete_id, created_at, 'recovery', 'checkin_completed', true, null from public.daily_checkins
 union all select id::text, athlete_id, created_at, 'history', 'session_logged', true, plan_id::text
 from public.session_logs where completed
 union all select id::text, athlete_id, created_at, 'plans', 'plan_created', true, id::text from public.custom_training_plans
 union all select id::text, submitted_by_profile_id, created_at, 'feedback', 'feedback_submitted', true, null
 from public.beta_feedback where surface='session'
 union all select id::text, athlete_id, created_at, 'plans', 'plan_generated', false, id::text from public.plans
 union all select id::text || ':onboarding-start', id, onboarding_started_at, 'onboarding', 'onboarding_started', false, null
 from public.profiles where onboarding_started_at is not null
 union all select id::text || ':onboarding-complete', id, onboarding_completed_at, 'onboarding', 'onboarding_completed', false, null
 from public.profiles where onboarding_completed_at is not null
 union all select id::text, athlete_id, created_at, feature, event_name,
 event_name in ('plan_edited','timer_started','timer_round_completed','timer_completed','nutrition_saved'), flow_id::text
 from public.product_events;
revoke all on public.product_activity from anon, authenticated;
grant select on public.product_activity to service_role;

-- SQL groups evidence before transfer; no free text enters the analytics service.
create function public.product_analytics_facts(p_excluded_emails text[] default '{}', p_athlete_id uuid default null)
returns jsonb language sql stable security invoker set search_path=public,pg_temp as $$
 with athletes as (
 select p.id, p.created_at, p.professional_status, p.technical_style, p.starting_path,
 (select min(created_at) from public.plans where athlete_id=p.id and status in ('ready','publishable_with_flags')) first_usable_plan_at
 from public.profiles p where (p_athlete_id is null and p.role='athlete' and not p.analytics_excluded
 and not (lower(btrim(p.email))=any(p_excluded_emails))
 and not exists(select 1 from public.product_analytics_excluded_emails x where x.email=lower(btrim(p.email)))) or p.id=p_athlete_id
 ), facts as (
 select a.athlete_id, (a.occurred_at at time zone 'UTC')::date as day, a.feature, a.action, a.meaningful,
 count(*) as count, min(a.occurred_at) as first_at, max(a.occurred_at) as last_at
 from public.product_activity a join athletes p on p.id=a.athlete_id
 where a.occurred_at <= now() group by 1,2,3,4,5
 ) select jsonb_build_object('athletes',coalesce((select jsonb_agg(to_jsonb(p)) from athletes p),'[]'::jsonb),
 'facts',coalesce((select jsonb_agg(to_jsonb(f)) from facts f),'[]'::jsonb),
 'timer_flows',coalesce((select jsonb_agg(x) from (
 select e.athlete_id,e.flow_id,min(e.created_at) filter(where event_name='timer_started') started_at,
 max(e.created_at) filter(where event_name='timer_completed') completed_at,
 max(e.created_at) filter(where event_name='timer_exited') exited_at
 from public.product_events e join athletes p on p.id=e.athlete_id where feature='timer' and flow_id is not null
 group by 1,2 having bool_or(event_name='timer_started')
 ) x),'[]'::jsonb),
 'plans_used',coalesce((select jsonb_agg(x) from (
 select pl.athlete_id,pl.created_at,exists(select 1 from public.product_activity a where a.athlete_id=pl.athlete_id and a.flow_id=pl.id::text and a.action<>'plan_generated' and a.occurred_at>=pl.created_at) interacted,exists(select 1 from public.session_completions c where c.plan_id=pl.id and c.status in ('done','modified') and c.completed_at>=pl.created_at) used
 from public.plans pl join athletes p on p.id=pl.athlete_id
 ) x),'[]'::jsonb),
 'sessions',coalesce((select jsonb_agg(x) from (
 select c.athlete_id,c.started_at,c.completed_at,c.status from public.session_completions c
 join athletes p on p.id=c.athlete_id
 ) x),'[]'::jsonb),
 'generation_errors',coalesce((select jsonb_agg(x) from (
 select j.athlete_id, (j.created_at at time zone 'UTC')::date as day, count(*) as count
 from public.generation_jobs j join athletes p on p.id=j.athlete_id where j.status='failed' group by 1,2
 ) x),'[]'::jsonb))
 $$;
revoke all on function public.product_analytics_facts(text[],uuid) from public, anon, authenticated;
grant execute on function public.product_analytics_facts(text[],uuid) to service_role;

create function public.prune_product_events() returns bigint language plpgsql security invoker
set search_path=public,pg_temp as $$ declare n bigint; begin
 delete from public.product_events where created_at < now()-interval '180 days';
 get diagnostics n=row_count; return n; end $$;
revoke all on function public.prune_product_events() from public,anon,authenticated;
grant execute on function public.prune_product_events() to service_role;

create table public.product_analytics_preferences (
 athlete_id uuid primary key references public.profiles(id) on delete cascade,
 enabled boolean not null default false,
 consent_version text not null default 'product-analytics-v1',
 updated_at timestamptz not null default now()
);
alter table public.product_analytics_preferences enable row level security;
revoke all on public.product_analytics_preferences from anon,authenticated;
grant all on public.product_analytics_preferences to service_role;
-- This tightly restricted catalog reader needs the scheduler owner's view of
-- cron jobs/run history. It exposes no commands, user records or write access.
create function public.product_analytics_retention_health()
returns jsonb language sql stable security definer set search_path=pg_catalog,pg_temp as $$
 with job as (
  select jobid from cron.job where jobname='product-events-retention'
    and active and schedule='17 3 * * *' and database=current_database()
    and command='select public.prune_product_events()'
 ), success as (
  select max(r.end_time) last_success_at from cron.job_run_details r join job j using(jobid)
  where r.status='succeeded'
 ), state as (
  select exists(select 1 from job) configured,success.last_success_at,
  (select status from cron.job_run_details r join job j using(jobid) order by r.start_time desc limit 1) last_status
  from success
 ) select jsonb_build_object('configured',configured,'last_success_at',last_success_at,'last_status',last_status,
  'healthy',configured and (
   coalesce(last_success_at>=now()-interval '36 hours',false) or
   (last_success_at is null and not exists(select 1 from public.product_events where created_at<now()-interval '36 hours'))
  )) from state;
$$;
revoke all on function public.product_analytics_retention_health() from public,anon,authenticated;
grant execute on function public.product_analytics_retention_health() to service_role;

-- Consent changes take the same lock as ingestion. A completed withdrawal
-- therefore cannot race an already-checked insert into storing a later event.
create function public.set_product_analytics_preference(p_athlete_id uuid,p_enabled boolean)
returns boolean language plpgsql security invoker set search_path=public,pg_temp as $$
begin
 perform pg_advisory_xact_lock(hashtextextended(p_athlete_id::text,0));
 if p_enabled and (not coalesce((public.product_analytics_retention_health()->>'healthy')::boolean,false)
  or not exists(select 1 from public.profiles where id=p_athlete_id and date_of_birth<=((now() at time zone 'UTC')::date-interval '18 years')::date)) then return false; end if;
 insert into public.product_analytics_preferences(athlete_id,enabled,consent_version,updated_at)
 values(p_athlete_id,p_enabled,'product-analytics-v1',now())
 on conflict(athlete_id) do update set enabled=excluded.enabled,consent_version=excluded.consent_version,updated_at=excluded.updated_at;
 return p_enabled;
end $$;
revoke all on function public.set_product_analytics_preference(uuid,boolean) from public,anon,authenticated;
grant execute on function public.set_product_analytics_preference(uuid,boolean) to service_role;

create function public.ingest_product_event(p_athlete_id uuid,p_event_name text,p_feature text,p_request_id uuid,p_flow_id uuid default null)
returns boolean language plpgsql security invoker set search_path=public,pg_temp as $$
begin
 -- Serialize the cap per athlete, including concurrent requests.
 perform pg_advisory_xact_lock(hashtextextended(p_athlete_id::text,0));
 if not exists(select 1 from public.product_analytics_preferences where athlete_id=p_athlete_id and enabled) then return false; end if;
 if exists(select 1 from public.profiles p join public.product_analytics_excluded_emails x on x.email=lower(btrim(p.email)) where p.id=p_athlete_id) then return false; end if;
 if not coalesce((public.product_analytics_retention_health()->>'healthy')::boolean,false) then return false; end if;
 if not exists(select 1 from public.profiles where id=p_athlete_id and date_of_birth<=((now() at time zone 'UTC')::date-interval '18 years')::date) then return false; end if;
 if (select count(*) from public.product_events where athlete_id=p_athlete_id and created_at>now()-interval '1 minute')>=120 then return false; end if;
 if (select count(*) from public.product_events where athlete_id=p_athlete_id and created_at >= date_trunc('day',now() at time zone 'UTC') at time zone 'UTC')>=1000 then return false; end if;
 insert into public.product_events(athlete_id,event_name,feature,request_id,flow_id)
 values(p_athlete_id,p_event_name,p_feature,p_request_id,p_flow_id) on conflict do nothing;
 return true;
end $$;
revoke all on function public.ingest_product_event(uuid,text,text,uuid,uuid) from public,anon,authenticated;
grant execute on function public.ingest_product_event(uuid,text,text,uuid,uuid) to service_role;
create index product_events_retention on public.product_events(created_at);
-- Use the required existing Supabase scheduler; no new scheduler dependency.
do $outer$ begin
 if exists(select 1 from pg_extension where extname='pg_cron') then
 perform cron.schedule('product-events-retention','17 3 * * *','select public.prune_product_events()');
 end if;
end $outer$;

create or replace view public.admin_athlete_rollups
with (security_invoker = true) as
select
  p.id,
  p.email,
  p.username,
  p.role,
  p.full_name,
  p.technical_style,
  p.tactical_style,
  p.stance,
  p.professional_status,
  p.record_summary,
  p.athlete_timezone,
  p.athlete_locale,
  p.appearance_mode,
  p.onboarding_draft,
  p.nutrition_profile,
  p.created_at,
  p.updated_at,
  count(pl.id)::int as plan_count,
  max(pl.created_at) as latest_plan_created_at,
  p.access_status,
  min(pl.created_at) filter (
    where pl.status in ('ready', 'publishable_with_flags')
  ) as first_usable_plan_at,
  (select max(a.occurred_at) from public.product_activity a where a.athlete_id=p.id and a.meaningful) as last_meaningful_activity_at
from public.profiles p
left join public.plans pl on pl.athlete_id = p.id
group by p.id;

revoke all on public.admin_athlete_rollups from anon, authenticated;
grant select on public.admin_athlete_rollups to service_role;

create unique index product_event_discovery_daily on public.product_events
(athlete_id,event_name,feature,(coalesce(flow_id,'00000000-0000-0000-0000-000000000000'::uuid)),((created_at at time zone 'UTC')::date))
where event_name in ('plan_opened','plan_editor_opened','history_opened','nutrition_opened','nutrition_saved','plan_edited','plan_replaced');

-- profiles retains legacy client UPDATE grants. Column REVOKE alone cannot
-- override a table-level grant: enforce these server-owned fields at the row
-- boundary as well, preserving every other existing profile write policy.
create or replace function private.prevent_client_product_analytics_profile_writes()
returns trigger language plpgsql security invoker set search_path=pg_catalog,pg_temp as $$
begin
 if auth.role() in ('anon','authenticated') then
  if tg_op='INSERT' then
   if new.analytics_excluded or new.onboarding_started_at is not null or new.onboarding_completed_at is not null then
    raise exception 'Analytics workflow fields are server-owned' using errcode='42501';
   end if;
  elsif new.analytics_excluded is distinct from old.analytics_excluded
     or new.onboarding_started_at is distinct from old.onboarding_started_at
     or new.onboarding_completed_at is distinct from old.onboarding_completed_at then
   raise exception 'Analytics workflow fields are server-owned' using errcode='42501';
  end if;
 end if;
 return new;
end $$;
revoke all on function private.prevent_client_product_analytics_profile_writes() from public,anon,authenticated;
create trigger prevent_client_product_analytics_profile_writes before insert or update on public.profiles
for each row execute function private.prevent_client_product_analytics_profile_writes();
