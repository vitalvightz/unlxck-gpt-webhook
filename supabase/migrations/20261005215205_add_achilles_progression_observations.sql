-- Reuse append-only episode observations, owner-select RLS and service-only RPC.
-- No changes to exposures, completion rows, prescriptions or clinical profiles.
alter table public.injury_episode_events drop constraint injury_episode_events_event_type_check;
alter table public.injury_episode_events add constraint injury_episode_events_event_type_check
  check (event_type in ('injury_checkin','delayed_rehab_response','clinician_clearance_report','rehab_progression_assessment'));

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
  if v_type <> 'delayed_rehab_response' and v_injury.episode_id is distinct from (p_event->>'injury_episode_id')::uuid then
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
              and e.injury_id = v_injury.id and e.injury_episode_id = (p_event->>'injury_episode_id')::uuid) then
      raise exception 'invalid delayed response' using errcode = '23514';
    end if;
  elsif v_type = 'rehab_progression_assessment' then
    -- Registered API code validates the typed protocol, clinical payload and
    -- computes medical_concern/observation_times. Recheck its injury context under the
    -- same athlete/episode lock so concurrent injury edits cannot misattribute it.
    if v_injury.status not in ('open','monitoring')
       or coalesce(v_payload->>'region','') = ''
       or coalesce(v_payload->>'injury_type','') = ''
       or coalesce(v_payload->>'profile_id','') = ''
       or v_payload->>'source' is distinct from 'athlete_reported'
       or v_payload->'externally_verified' is distinct from 'false'::jsonb
       or jsonb_typeof(v_payload->'assessment') is distinct from 'object'
       or v_payload->'assessment'->'schema_version' is distinct from '1'::jsonb
       or coalesce(v_payload->'assessment'->>'assessment_kind','') !~ '^[a-z0-9]+(_[a-z0-9]+)*$'
       or coalesce(v_payload->'assessment'->>'protocol_version','') !~ '^[1-9][0-9]*$'
       or jsonb_typeof(v_payload->'assessment'->'protocol_version') is distinct from 'number'
       or jsonb_typeof(v_payload->'assessment'->'payload') is distinct from 'object'
       or jsonb_typeof(v_payload->'medical_concern') is distinct from 'boolean'
       or v_payload->'injury_context'->>'body_area' is distinct from v_injury.body_area
       or v_payload->'injury_context'->>'description' is distinct from v_injury.description
       or v_payload->'assessment'->>'side' is distinct from v_injury.side
       or coalesce(v_payload->'assessment'->>'assessor','') not in ('self_reported','clinician_physio','coach_observed','unknown')
       or coalesce(v_payload->'assessment'->>'assessed_at','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
       or (v_payload->'assessment'->>'assessed_at')::timestamptz > now()
       or (v_payload->'assessment'->>'assessed_at')::timestamptz < v_injury.created_at
       or jsonb_typeof(v_payload->'observation_times') is distinct from 'array'
       or jsonb_array_length(v_payload->'observation_times') = 0 then
      raise exception 'invalid progression assessment envelope' using errcode = '23514';
    end if;
    if exists (select 1 from jsonb_array_elements_text(v_payload->'observation_times') t
               where t !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' or t::timestamptz > now() or t::timestamptz < v_injury.created_at) then
      raise exception 'invalid progression assessment timestamps' using errcode = '23514';
    end if;
  else raise exception 'unknown episode event' using errcode = '22023';
  end if;
  insert into public.injury_episode_events (id, athlete_id, injury_id, injury_episode_id, event_type, payload)
    values ((p_event->>'id')::uuid, p_athlete_id, v_injury.id, (p_event->>'injury_episode_id')::uuid, v_type, v_payload)
    on conflict (id) do nothing returning * into v_result;
  if found and v_type = 'rehab_progression_assessment' and v_payload->'medical_concern' = 'true'::jsonb then
    update public.injury_flags set updated_at = clock_timestamp() where id = v_injury.id;
  end if;
  if v_result.id is null then
    select * into v_result from public.injury_episode_events where id = (p_event->>'id')::uuid and athlete_id = p_athlete_id;
    if not found or v_result.payload <> v_payload or v_result.event_type <> v_type
       or v_result.injury_id <> v_injury.id or v_result.injury_episode_id <> (p_event->>'injury_episode_id')::uuid then
      raise exception 'episode_event_conflict' using errcode = '23514';
    end if;
  end if;
  return v_result;
end;
$$;
revoke all on function public.record_injury_episode_event(uuid, jsonb) from public, anon, authenticated;
grant execute on function public.record_injury_episode_event(uuid, jsonb) to service_role;

