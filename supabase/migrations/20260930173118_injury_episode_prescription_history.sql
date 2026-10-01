-- Server-owned prescriptions and append-only observations. Ownership mirrors
-- injury_flags / rehab_exposures; an athlete report is not verified clearance.
grant select on public.rehab_exposures to service_role;
alter table public.session_completions
  add column if not exists prescription_snapshot jsonb
    check (prescription_snapshot is null or jsonb_typeof(prescription_snapshot) = 'object'),
  add column if not exists rehab_performance text
    check (rehab_performance in ('done_as_shown', 'changed', 'stopped'));

create or replace function public.lock_injury_prescription_context()
returns trigger language plpgsql set search_path = public, pg_temp as $$
begin
  if tg_op = 'DELETE' then
    perform pg_advisory_xact_lock(hashtextextended('injury:' || old.athlete_id::text, 0));
    return old;
  end if;
  perform pg_advisory_xact_lock(hashtextextended('injury:' || new.athlete_id::text, 0));
  return new;
end;
$$;
drop trigger if exists lock_injury_prescription_context on public.injury_flags;
create trigger lock_injury_prescription_context before insert or update or delete
  on public.injury_flags for each row execute function public.lock_injury_prescription_context();
drop trigger if exists lock_injury_prescription_context on public.today_checkins;
create trigger lock_injury_prescription_context before insert or update or delete
  on public.today_checkins for each row execute function public.lock_injury_prescription_context();

create or replace function public.preserve_started_prescription()
returns trigger language plpgsql set search_path = public, pg_temp as $$
declare
  v_block jsonb;
  v_limit int;
  v_used int;
begin
  if new.prescription_snapshot is not null or (tg_op = 'UPDATE' and old.prescription_snapshot is not null) then
    perform pg_advisory_xact_lock(hashtextextended('injury:' || new.athlete_id::text, 0));
  end if;
  -- INSERT ... ON CONFLICT runs the insert trigger before the update trigger.
  -- The existing occurrence is validated by the UPDATE branch with its real id.
  if tg_op = 'INSERT' and exists (select 1 from public.session_completions s
     where s.athlete_id = new.athlete_id and s.session_id = new.session_id and s.training_day = new.training_day) then
    return new;
  end if;
  if tg_op = 'UPDATE' and old.prescription_snapshot is not null then
    if old.status in ('done','modified') and new.status not in ('done','modified')
       and exists (select 1 from jsonb_array_elements(old.prescription_snapshot->'session'->'blocks') b where b ? 'policy_id') then
      raise exception 'rehab_exposure_cannot_be_reset' using errcode = '23514';
    end if;
    if new.prescription_snapshot is not null and new.prescription_snapshot <> old.prescription_snapshot then
      raise exception 'prescription_revision_conflict' using errcode = '23514';
    end if;
    new.prescription_snapshot := old.prescription_snapshot;
  end if;
  if new.prescription_snapshot is not null then
    if new.prescription_snapshot->>'plan_id' is distinct from new.plan_id::text
       or new.prescription_snapshot->>'training_day' is distinct from new.training_day::text
       or new.prescription_snapshot->'session'->>'session_id' is distinct from new.session_id
       or coalesce(new.prescription_snapshot->>'revision', '') !~ '^[a-f0-9]{64}$' then
      raise exception 'invalid prescription occurrence' using errcode = '23514';
    end if;
    if tg_op = 'INSERT' or old.prescription_snapshot is null then
      perform pg_advisory_xact_lock(hashtextextended('injury:' || new.athlete_id::text, 0));
      if new.prescription_snapshot->'evidence_context'->>'exposure_id' is distinct from
         (select id::text from public.rehab_exposures where athlete_id = new.athlete_id order by created_at desc, id desc limit 1)
         or new.prescription_snapshot->'evidence_context'->>'event_id' is distinct from
         (select id::text from public.injury_episode_events where athlete_id = new.athlete_id
           and event_type in ('injury_checkin','delayed_rehab_response') order by created_at desc, id desc limit 1) then
        raise exception 'prescription_revision_conflict' using errcode = '23514';
      end if;
      if jsonb_typeof(new.prescription_snapshot->'readiness_context') is distinct from 'object'
         or not exists (select 1 from public.today_checkins c
           where c.athlete_id = new.athlete_id and c.plan_id = new.plan_id
             and c.training_day = new.training_day
             and c.id = (new.prescription_snapshot->'readiness_context'->>'id')::uuid
             and c.updated_at is not distinct from
               (new.prescription_snapshot->'readiness_context'->>'updated_at')::timestamptz) then
        raise exception 'prescription_revision_conflict' using errcode = '23514';
      end if;
      if jsonb_typeof(new.prescription_snapshot->'injury_context') is distinct from 'array'
         or (select count(*) from public.injury_flags where athlete_id = new.athlete_id and status in ('open','monitoring'))
            <> jsonb_array_length(new.prescription_snapshot->'injury_context')
         or exists (select 1 from jsonb_array_elements(new.prescription_snapshot->'injury_context') c
             where not exists (select 1 from public.injury_flags i
               where i.athlete_id = new.athlete_id and i.id = (c->>'id')::uuid
                 and i.episode_id = (c->>'episode_id')::uuid and i.status in ('open','monitoring')
                 and i.updated_at is not distinct from (c->>'updated_at')::timestamptz)) then
        raise exception 'prescription_revision_conflict' using errcode = '23514';
      end if;
    end if;
    if new.status in ('started','done','modified') then
      v_limit := coalesce((new.prescription_snapshot->>'allocation_limit')::int, 2);
      if v_limit not between 1 and 2 then raise exception 'invalid rehab allocation' using errcode = '23514'; end if;
      select count(*) into v_used from public.session_completions s,
        lateral jsonb_array_elements(s.prescription_snapshot->'session'->'blocks') b
        where s.athlete_id = new.athlete_id and s.training_day = new.training_day
          and s.status in ('started','done','modified') and s.id <> new.id and b->>'block_type' = 'rehab';
      if exists (select 1 from jsonb_array_elements(new.prescription_snapshot->'session'->'blocks') b where b->>'block_type' = 'rehab')
         and v_used + (select count(*) from jsonb_array_elements(new.prescription_snapshot->'session'->'blocks') b where b->>'block_type' = 'rehab') > v_limit then
        raise exception 'rehab_daily_allocation_conflict' using errcode = '23514';
      end if;
      for v_block in select b from jsonb_array_elements(new.prescription_snapshot->'session'->'blocks') b where b ? 'policy_id' loop
        if exists (select 1 from public.session_completions s,
             lateral jsonb_array_elements(s.prescription_snapshot->'session'->'blocks') b
             where s.athlete_id = new.athlete_id and s.id <> new.id and s.status in ('started','done','modified')
               and b->>'injury_id' = v_block->>'injury_id' and b->>'injury_episode_id' = v_block->>'injury_episode_id'
               and (s.training_day = new.training_day or
                 (s.status in ('done','modified') and b->>'rehab_drill_id' = v_block->>'rehab_drill_id'
                   and s.training_day <= new.training_day
                   and s.training_day + greatest(coalesce((b->>'minimum_gap_days')::int,1), (v_block->>'minimum_gap_days')::int) > new.training_day))) then
          raise exception 'rehab_daily_allocation_conflict' using errcode = '23514';
        end if;
      end loop;
    end if;
  end if;
  return new;
end;
$$;
drop trigger if exists preserve_started_prescription on public.session_completions;
create trigger preserve_started_prescription before insert or update
  on public.session_completions for each row execute function public.preserve_started_prescription();

create unique index if not exists injury_flags_owner_identity_idx on public.injury_flags (id, athlete_id);
create table if not exists public.injury_episode_events (
  id uuid primary key,
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  injury_id uuid not null,
  injury_episode_id uuid not null,
  event_type text not null check (event_type in ('clinician_clearance_report', 'delayed_rehab_response', 'injury_checkin')),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  created_at timestamptz not null default now(),
  foreign key (injury_id, athlete_id) references public.injury_flags (id, athlete_id) on delete cascade
);
create index if not exists injury_episode_events_history_idx on public.injury_episode_events (athlete_id, injury_id, injury_episode_id, created_at desc);
create unique index if not exists injury_episode_events_delayed_once_idx on public.injury_episode_events
  (athlete_id, (payload->>'exposure_id')) where event_type = 'delayed_rehab_response';
alter table public.injury_episode_events enable row level security;
drop policy if exists injury_episode_events_owner_select on public.injury_episode_events;
create policy injury_episode_events_owner_select on public.injury_episode_events
  for select to authenticated using ((select auth.uid()) = athlete_id);
revoke all on public.injury_episode_events from anon, authenticated, service_role;
grant select on public.injury_episode_events to authenticated, service_role;

create or replace function public.capture_injury_episode_change()
returns trigger language plpgsql security definer set search_path = public, pg_temp as $$
begin
  if tg_op = 'UPDATE' and new.status is not distinct from old.status
     and new.latest_reported_status is not distinct from old.latest_reported_status
     and new.severity is not distinct from old.severity and new.episode_id = old.episode_id then
    return new;
  end if;
  insert into public.injury_episode_events (id, athlete_id, injury_id, injury_episode_id, event_type, payload)
    values (gen_random_uuid(), new.athlete_id, new.id, new.episode_id, 'injury_checkin',
      jsonb_build_object('status', new.status, 'latest_reported_status', new.latest_reported_status,
                         'severity', new.severity, 'source', new.source));
  return new;
end;
$$;
drop trigger if exists capture_injury_episode_change on public.injury_flags;
create trigger capture_injury_episode_change after insert or update on public.injury_flags
  for each row execute function public.capture_injury_episode_change();

create or replace function public.record_injury_episode_event(p_athlete_id uuid, p_event jsonb)
returns public.injury_episode_events language plpgsql security definer
set search_path = public, pg_temp as $$
declare
  v_injury public.injury_flags%rowtype;
  v_result public.injury_episode_events%rowtype;
  v_type text := p_event->>'event_type';
  v_payload jsonb := p_event->'payload';
begin
  -- Always take the athlete lock before any injury row lock.
  perform pg_advisory_xact_lock(hashtextextended('injury:' || p_athlete_id::text, 0));
  select * into v_injury from public.injury_flags
    where id = (p_event->>'injury_id')::uuid and athlete_id = p_athlete_id for share;
  if not found then raise exception 'injury not found' using errcode = '23503'; end if;
  if v_injury.episode_id <> (p_event->>'injury_episode_id')::uuid then
    raise exception 'injury_episode_changed' using errcode = '23514';
  end if;
  if v_type = 'clinician_clearance_report' then
    if v_payload->>'source' is distinct from 'athlete_reported'
       or v_payload->>'externally_verified' is distinct from 'false'
       or jsonb_typeof(v_payload->'scopes') is distinct from 'array'
       or jsonb_array_length(v_payload->'scopes') = 0
       or exists (select 1 from jsonb_array_elements_text(v_payload->'scopes') s
                  where s not in ('rehab','training','contact')) then
      raise exception 'invalid clearance report' using errcode = '22023';
    end if;
  elsif v_type = 'delayed_rehab_response' then
    if coalesce(v_payload->>'response','') not in ('better','same','worse','not_sure')
       or not exists (select 1 from public.rehab_exposures e
            where e.id = (v_payload->>'exposure_id')::uuid and e.athlete_id = p_athlete_id
              and e.injury_id = v_injury.id and e.injury_episode_id = v_injury.episode_id) then
      raise exception 'invalid delayed response' using errcode = '23514';
    end if;
  else raise exception 'unknown episode event' using errcode = '22023';
  end if;
  insert into public.injury_episode_events (id, athlete_id, injury_id, injury_episode_id, event_type, payload)
    values ((p_event->>'id')::uuid, p_athlete_id, v_injury.id, v_injury.episode_id, v_type, v_payload)
    on conflict (id) do nothing returning * into v_result;
  if not found then
    select * into v_result from public.injury_episode_events where id = (p_event->>'id')::uuid and athlete_id = p_athlete_id;
    if not found or v_result.payload <> v_payload or v_result.event_type <> v_type
       or v_result.injury_id <> v_injury.id or v_result.injury_episode_id <> v_injury.episode_id then
      raise exception 'episode_event_conflict' using errcode = '23514';
    end if;
  end if;
  return v_result;
end;
$$;
revoke all on function public.record_injury_episode_event(uuid, jsonb) from public, anon, authenticated;
grant execute on function public.record_injury_episode_event(uuid, jsonb) to service_role;

-- Unanswered rows remain discoverable regardless of how many newer sessions
-- exist. Bounded batches drain oldest first, never dropping durable prompts.
create or replace function public.pending_delayed_rehab(p_athlete_id uuid, p_training_day date)
returns setof public.rehab_exposures language sql security definer
set search_path = public, pg_temp as $$
  select e.* from public.rehab_exposures e
    join public.injury_flags i on i.id = e.injury_id and i.athlete_id = e.athlete_id and i.episode_id = e.injury_episode_id
    where e.athlete_id = p_athlete_id and e.occurred_at::date < p_training_day
      and coalesce(e.response->>'next_day_response','not_yet_known') = 'not_yet_known'
      and not exists (select 1 from public.injury_episode_events o
         where o.athlete_id = e.athlete_id and o.event_type = 'delayed_rehab_response' and o.payload->>'exposure_id' = e.id::text)
    order by e.occurred_at, e.id limit 100;
$$;
revoke all on function public.pending_delayed_rehab(uuid, date) from public, anon, authenticated;
grant execute on function public.pending_delayed_rehab(uuid, date) to service_role;

-- Historical evidence must survive a resolved flag starting a new episode.
-- The RPC validates the current episode while holding the injury row; the FK
-- enforces ownership without binding old observations to the latest episode.
do $$
 declare v_constraint record;
 begin
   for v_constraint in select c.conname from pg_constraint c
     where c.conrelid = 'public.rehab_exposures'::regclass and c.contype = 'f'
       and c.confrelid = 'public.injury_flags'::regclass
       and exists (select 1 from pg_attribute a where a.attrelid = c.conrelid
                    and a.attnum = any(c.conkey) and a.attname = 'injury_episode_id')
   loop execute format('alter table public.rehab_exposures drop constraint %I', v_constraint.conname); end loop;
   if not exists (select 1 from pg_constraint where conrelid = 'public.rehab_exposures'::regclass
                   and conname = 'rehab_exposures_injury_owner_fkey') then
     alter table public.rehab_exposures add constraint rehab_exposures_injury_owner_fkey
       foreign key (injury_id, athlete_id) references public.injury_flags (id, athlete_id) on delete cascade;
   end if;
 end;
$$;

-- Session completion proves that a rehab exposure occurred, but it does not
-- quantify every drill. Admit an explicit unquantified completion state at the
-- database boundary while retaining every identity, demand and response check
-- from the prior RPC revision.
create or replace function public.record_rehab_exposure(p_athlete_id uuid, p_event jsonb)
returns public.rehab_exposures
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_injury public.injury_flags%rowtype;
  v_existing public.rehab_exposures%rowtype;
  v_result public.rehab_exposures%rowtype;
  v_demand jsonb := p_event->'demand';
  v_completed jsonb := p_event->'dose_completed';
  v_response jsonb := coalesce(p_event->'response', '{}'::jsonb);
  v_side text := p_event->>'side';
  v_region text := p_event->>'body_region';
  v_completion_state text := v_completed->>'completion_state';
  v_key text;
  v_pain jsonb;
  v_region_guidance boolean;
begin
  if p_event is null or jsonb_typeof(p_event) <> 'object'
     or jsonb_typeof(v_demand) <> 'object'
     or jsonb_typeof(v_completed) <> 'object'
     or jsonb_typeof(v_response) <> 'object' then
    raise exception 'invalid rehab exposure object' using errcode = '22023';
  end if;

  -- Always take the athlete lock before any injury row lock.
  perform pg_advisory_xact_lock(hashtextextended('injury:' || p_athlete_id::text, 0));
  select * into v_injury from public.injury_flags
   where id = (p_event->>'injury_id')::uuid and athlete_id = p_athlete_id for share;
  if not found then raise exception 'injury not found' using errcode = '23503'; end if;
  -- Unknown side is retained only for baseline region-wide guidance accepted
  -- in an exact frozen episode. Unattributed legacy exercise stays ineligible.
  v_region_guidance := v_injury.side = 'unknown' and v_side = 'unknown' and exists (
    select 1 from public.session_completions s,
      lateral jsonb_array_elements(s.prescription_snapshot->'session'->'blocks') b
      where s.athlete_id = p_athlete_id and s.status in ('done','modified')
        and s.prescription_snapshot->>'revision' = p_event#>>'{provenance,prescription_revision}'
        and b->>'injury_id' = p_event->>'injury_id' and b->>'injury_episode_id' = p_event->>'injury_episode_id'
        and b->>'rehab_drill_id' = p_event->>'drill_id'
        and b->>'policy_id' in ('chest_strain','ankle_sprain')
        and b->'drill_snapshot'->>'rehab_stage' in ('calm','restore')
        and b->'drill_snapshot'->>'laterality_applicability' = 'not_applicable');
  if coalesce(v_side, '') not in ('left','right','bilateral','unknown')
     or v_injury.episode_id <> (p_event->>'injury_episode_id')::uuid
     or v_injury.body_region is null or v_injury.body_region <> v_region
     or ((v_injury.side = 'unknown' or v_side = 'unknown') and not v_region_guidance)
     or not (v_injury.side = v_side or v_injury.side = 'bilateral' or v_side = 'bilateral') then
    raise exception 'exposure does not match injury episode, region and side' using errcode = '23514';
  end if;

  -- Unknown demand remains a valid observation but is never capacity evidence;
  -- RehabExposureEvent.has_unknown_demand keeps it non-qualifying downstream.
  if coalesce(v_demand->>'load','') not in ('unknown','minimal','low','moderate','high')
     or coalesce(v_demand->>'impact','') not in ('unknown','none','low','moderate','high')
     or coalesce(v_demand->>'velocity','') not in ('unknown','low','moderate','high')
     or jsonb_typeof(v_demand->'target_regions') <> 'array'
     or not (v_demand->'target_regions' ? v_region) then
    raise exception 'invalid exposure demand' using errcode = '23514';
  end if;

  if v_completed = '{}'::jsonb or not exists (
    select 1 from jsonb_each(v_completed) item where jsonb_typeof(item.value) <> 'null'
  ) then
    raise exception 'completed dose is empty' using errcode = '23514';
  end if;
  for v_key in select jsonb_object_keys(v_completed) loop
    if v_key not in ('sets','reps','duration_seconds','external_load_kg','distance_metres','hold_seconds','completed_fraction','stopped_early','completion_state') then
      raise exception 'invalid completed dose field' using errcode = '23514';
    end if;
  end loop;
  foreach v_key in array array['sets','reps','duration_seconds','external_load_kg','distance_metres','hold_seconds','completed_fraction'] loop
    if v_completed ? v_key and jsonb_typeof(v_completed->v_key) <> 'null'
       and (jsonb_typeof(v_completed->v_key) <> 'number' or (v_completed->>v_key)::numeric < 0) then
      raise exception 'invalid completed dose value' using errcode = '23514';
    end if;
  end loop;
  if v_completed ? 'completed_fraction' and jsonb_typeof(v_completed->'completed_fraction') <> 'null'
     and (v_completed->>'completed_fraction')::numeric > 1 then
    raise exception 'invalid completed fraction' using errcode = '23514';
  end if;
  if v_completed ? 'stopped_early' and jsonb_typeof(v_completed->'stopped_early') not in ('boolean','null') then
    raise exception 'invalid stopped_early' using errcode = '23514';
  end if;
  if v_completed ? 'completion_state'
     and coalesce(v_completion_state, '') not in ('performed_amount_unknown','partial_amount_unknown','quantified') then
    raise exception 'invalid completion state' using errcode = '23514';
  end if;
  if v_completion_state in ('performed_amount_unknown','partial_amount_unknown') and exists (
    select 1
    from jsonb_each(v_completed) item
    where item.key in ('sets','reps','duration_seconds','external_load_kg','distance_metres','hold_seconds','completed_fraction')
      and jsonb_typeof(item.value) <> 'null'
  ) then
    raise exception 'unquantified completion state contains a measured amount' using errcode = '23514';
  end if;
  if v_completion_state = 'quantified' and not exists (
    select 1
    from jsonb_each(v_completed) item
    where item.key in ('sets','reps','duration_seconds','external_load_kg','distance_metres','hold_seconds','completed_fraction')
      and jsonb_typeof(item.value) = 'number'
  ) then
    raise exception 'quantified completion state lacks a measured amount' using errcode = '23514';
  end if;

  foreach v_key in array array['pain_during','pain_immediate_after'] loop
    v_pain := v_response->v_key;
    if v_pain is not null and jsonb_typeof(v_pain) <> 'null'
       and not (jsonb_typeof(v_pain) = 'string' and v_pain #>> '{}' = 'not_sure')
       and not (jsonb_typeof(v_pain) = 'number' and (v_pain #>> '{}')::numeric between 0 and 10) then
      raise exception 'invalid injury-specific pain response' using errcode = '23514';
    end if;
  end loop;
  if coalesce(v_response->>'next_day_response','not_yet_known') not in ('better','same','worse','not_yet_known','not_sure') then
    raise exception 'invalid next-day response' using errcode = '23514';
  end if;
  if coalesce(v_response->>'during_response','not_reported') not in ('better','same','worse','not_sure','not_reported') then
    raise exception 'invalid during-work response' using errcode = '23514';
  end if;
  foreach v_key in array array['stopped_due_to_symptoms','worsening_reported'] loop
    if v_response ? v_key and jsonb_typeof(v_response->v_key) not in ('boolean','null') then
      raise exception 'invalid response flag' using errcode = '23514';
    end if;
  end loop;

  select * into v_existing from public.rehab_exposures where id = (p_event->>'exposure_id')::uuid;
  if found then
    if v_existing.athlete_id <> p_athlete_id or v_existing.event_json <> p_event then
      raise exception 'exposure id already used with different evidence' using errcode = '23505';
    end if;
    return v_existing;
  end if;

  insert into public.rehab_exposures (
    id, athlete_id, injury_id, injury_episode_id, drill_id, body_region, side,
    demand, prescribed_dose, completed_dose, response, event_json,
    evidence_source, occurred_at, recorded_at
  ) values (
    (p_event->>'exposure_id')::uuid, p_athlete_id, (p_event->>'injury_id')::uuid,
    (p_event->>'injury_episode_id')::uuid, p_event->>'drill_id', v_region, v_side,
    v_demand, p_event->'prescribed_dose', v_completed, v_response, p_event,
    p_event#>>'{provenance,source}', (p_event->>'occurred_at')::timestamptz,
    (p_event#>>'{provenance,recorded_at}')::timestamptz
  ) returning * into v_result;
  return v_result;
end;
$$;

revoke all on function public.record_rehab_exposure(uuid, jsonb) from public, anon, authenticated;
grant execute on function public.record_rehab_exposure(uuid, jsonb) to service_role;
