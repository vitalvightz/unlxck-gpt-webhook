-- Reuse append-only episode observations, owner-select RLS and service-only RPC.
-- No changes to exposures, completion rows, prescriptions or clinical profiles.
alter table public.injury_episode_events drop constraint injury_episode_events_event_type_check;
alter table public.injury_episode_events add constraint injury_episode_events_event_type_check
  check (event_type in ('injury_checkin','delayed_rehab_response','clinician_clearance_report','achilles_progression_input'));

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
  elsif v_type = 'achilles_progression_input' then
    -- API resolves exact tendonitis identity; recheck its text context under the
    -- same athlete/episode lock so concurrent injury edits cannot misattribute it.
    if v_injury.status not in ('open','monitoring')
       or v_payload->>'region' is distinct from 'achilles'
       or v_payload->>'injury_type' is distinct from 'tendonitis'
       or v_payload->>'source' is distinct from 'athlete_reported'
       or v_payload->'externally_verified' is distinct from 'false'::jsonb
       or jsonb_typeof(v_payload->'assessment') is distinct from 'object'
       or v_payload->'injury_context'->>'body_area' is distinct from v_injury.body_area
       or v_payload->'injury_context'->>'description' is distinct from v_injury.description
       or v_payload->'assessment'->>'side' is distinct from v_injury.side
       or coalesce(v_payload->'assessment'->>'assessor','') not in ('self_reported','clinician_physio','coach_observed','unknown')
       or coalesce(v_payload->'assessment'->>'site','') not in ('midportion','insertional','unknown')
       or (v_payload->'assessment'->>'assessed_at')::timestamptz > now()
       or (v_payload->'assessment'->>'assessed_at')::timestamptz < v_injury.created_at
       or nullif(v_payload->'assessment'->>'assessed_at','') is null
       or (v_payload->'assessment'->>'loading_performed_at')::timestamptz > now()
       or (v_payload->'assessment'->>'delayed_response_at')::timestamptz > now() then
      raise exception 'invalid Achilles episode observation' using errcode = '23514';
    end if;
  else raise exception 'unknown episode event' using errcode = '22023';
  end if;
  insert into public.injury_episode_events (id, athlete_id, injury_id, injury_episode_id, event_type, payload)
    values ((p_event->>'id')::uuid, p_athlete_id, v_injury.id, (p_event->>'injury_episode_id')::uuid, v_type, v_payload)
    on conflict (id) do nothing returning * into v_result;
  if found and v_type = 'achilles_progression_input' and (
      v_payload->'assessment'->>'incompatible_pathology' = 'suspected'
      or v_payload->'assessment'->>'suspected_rupture' = 'true'
      or v_payload->'assessment'->>'marked_weakness' = 'true'
      or v_payload->'assessment'->>'traumatic_loss_of_function' = 'true'
      or v_payload->'assessment'->>'clinician_restriction' = 'true') then
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

