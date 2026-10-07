-- Shared private clinical history. Python validates clinical interpretation;
-- SQL owns permissions, exact state CAS, append-only history and lock ordering.
alter table public.injury_episode_events drop constraint injury_episode_events_event_type_check;
alter table public.injury_episode_events add constraint injury_episode_events_event_type_check check
  (event_type in ('injury_checkin','delayed_rehab_response','clinician_clearance_report',
    'rehab_progression_assessment','clinical_progression_review','clinical_progression_review_lifecycle'));
alter table public.injury_episode_events add column if not exists clinical_capture jsonb;
alter table public.injury_episode_events drop constraint if exists clinical_capture_boundary;
alter table public.injury_episode_events add constraint clinical_capture_boundary check
  ((event_type in ('clinical_progression_review','clinical_progression_review_lifecycle')
    and jsonb_typeof(clinical_capture) = 'object' and clinical_capture is not null)
   or (event_type not in ('clinical_progression_review','clinical_progression_review_lifecycle') and clinical_capture is null));

drop policy if exists injury_episode_events_owner_select on public.injury_episode_events;
create policy injury_episode_events_owner_select on public.injury_episode_events for select to authenticated
  using ((select auth.uid()) = athlete_id and event_type not in
    ('clinical_progression_review','clinical_progression_review_lifecycle'));

create unique index if not exists clinical_review_replacement_once on public.injury_episode_events
  (athlete_id, injury_id, injury_episode_id, (payload->>'supersedes_review_id'))
  where event_type = 'clinical_progression_review' and payload->>'supersedes_review_id' is not null;
create unique index if not exists clinical_review_lifecycle_once on public.injury_episode_events
  (athlete_id, injury_id, injury_episode_id, (payload->>'review_id'), (payload->>'state'))
  where event_type = 'clinical_progression_review_lifecycle';

create or replace function public.preserve_clinical_review_history()
returns trigger language plpgsql set search_path = public, pg_temp as $$
begin
  if old.event_type in ('clinical_progression_review','clinical_progression_review_lifecycle') then
    raise exception 'clinical_review_history_immutable' using errcode = '23514';
  end if;
  return new;
end;
$$;
drop trigger if exists preserve_clinical_review_history on public.injury_episode_events;
create trigger preserve_clinical_review_history before update on public.injury_episode_events
  for each row execute function public.preserve_clinical_review_history();
revoke all on function public.preserve_clinical_review_history() from public, anon, authenticated, service_role;

create or replace function public.clinical_review_capture_context(p_athlete_id uuid, p_injury_id uuid, p_episode_id uuid)
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare
  v_profile jsonb;
  v_injury jsonb;
  v_events jsonb;
  v_exposures jsonb;
begin
  perform pg_advisory_xact_lock(hashtextextended('injury:' || p_athlete_id::text, 0));
  select to_jsonb(p) into v_profile from public.profiles p where id = p_athlete_id for share;
  select to_jsonb(i) into v_injury from public.injury_flags i
    where id = p_injury_id and athlete_id = p_athlete_id for share;
  if v_profile is null or v_injury is null or v_injury->>'episode_id' is distinct from p_episode_id::text then
    raise exception 'clinical_review_episode_changed' using errcode = '23514';
  end if;
  select coalesce(jsonb_agg(to_jsonb(e) order by e.created_at, e.id), '[]') into v_events
    from public.injury_episode_events e where athlete_id = p_athlete_id and injury_id = p_injury_id and injury_episode_id = p_episode_id;
  select coalesce(jsonb_agg(to_jsonb(e) order by e.created_at, e.id), '[]') into v_exposures
    from public.rehab_exposures e where athlete_id = p_athlete_id and injury_id = p_injury_id and injury_episode_id = p_episode_id;
  return jsonb_build_object('profile',v_profile,'injury',v_injury,'events',v_events,'exposures',v_exposures);
end;
$$;
revoke all on function public.clinical_review_capture_context(uuid,uuid,uuid) from public, anon, authenticated;
grant execute on function public.clinical_review_capture_context(uuid,uuid,uuid) to service_role;

create or replace function public.record_clinical_review_event(p_athlete_id uuid, p_recorder_id uuid,
  p_context jsonb, p_event jsonb, p_supersession jsonb default null)
returns public.injury_episode_events language plpgsql security definer set search_path = public, pg_temp as $$
declare
  v_current jsonb;
  v_result public.injury_episode_events%rowtype;
  v_prior public.injury_episode_events%rowtype;
  v_latest public.injury_episode_events%rowtype;
  v_replacement public.injury_episode_events%rowtype;
  v_envelope jsonb := p_event->'payload';
  v_meta jsonb := p_event->'clinical_capture';
  v_provenance jsonb := v_envelope->'provenance';
  v_injury_id uuid := (p_event->>'injury_id')::uuid;
  v_episode_id uuid := (p_event->>'injury_episode_id')::uuid;
  v_type text := p_event->>'event_type';
  v_identity uuid := (p_event->>'id')::uuid;
  v_old_id text;
begin
  perform pg_advisory_xact_lock(hashtextextended('injury:' || p_athlete_id::text, 0));
  -- Service role is transport authority, never proof of API admin authorisation.
  -- The API also checks the email allowlist; SQL rechecks the stored role.
  perform 1 from public.profiles where id = p_recorder_id and role = 'admin' for share;
  if not found or p_recorder_id = p_athlete_id then
    raise exception 'clinical_review_admin_required' using errcode = '42501';
  end if;
  v_current := public.clinical_review_capture_context(p_athlete_id,v_injury_id,v_episode_id);
  if v_current->'profile'->>'role' is distinct from 'athlete'
     or v_current->'profile'->>'access_status' is distinct from 'approved'
     or v_current->'profile'->'health_data_consent' is distinct from 'true'::jsonb
     or v_current->'profile'->>'health_consent_at' is null
     or (v_current->'profile'->>'health_consent_withdrawn_at' is not null and
       (v_current->'profile'->>'health_consent_withdrawn_at')::timestamptz >=
       (v_current->'profile'->>'health_consent_at')::timestamptz) then
    raise exception 'clinical_review_target_access_required' using errcode = '42501';
  end if;
  if coalesce(v_type,'') not in ('clinical_progression_review','clinical_progression_review_lifecycle')
     or p_event->>'athlete_id' is distinct from p_athlete_id::text
     or v_envelope->'schema_version' is distinct from '1'::jsonb
     or jsonb_typeof(v_envelope) is distinct from 'object'
     or v_meta->>'policy' is distinct from 'authenticated_admin_independent_confirmation_v1'
     or v_meta->>'recorder_id' is distinct from p_recorder_id::text
     or coalesce(v_meta->>'request_hash','') !~ '^[a-f0-9]{64}$'
     or coalesce(v_meta->>'envelope_hash','') !~ '^[a-f0-9]{64}$'
     or v_provenance->>'source' is distinct from 'independently_confirmed_clinician_statement'
     or v_provenance->'recorder'->>'actor_id' is distinct from p_recorder_id::text
     or v_provenance->'recorder'->>'role' is distinct from 'operational_recorder'
     or v_provenance->'verifier' is distinct from v_provenance->'recorder'
     or coalesce(v_provenance->>'confirmation_reference','') = ''
     or coalesce(v_provenance->>'statement_hash','') !~ '^[a-f0-9]{64}$'
     or coalesce(v_envelope->>'recorded_at','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
     or coalesce(v_provenance->>'confirmed_at','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
     or (v_envelope->>'recorded_at')::timestamptz > clock_timestamp()
     or (v_provenance->>'confirmed_at')::timestamptz > (v_envelope->>'recorded_at')::timestamptz then
    raise exception 'invalid clinical capture envelope' using errcode = '22023';
  end if;
  select * into v_result from public.injury_episode_events where id = v_identity;
  if found then
    if (v_result.athlete_id,v_result.injury_id,v_result.injury_episode_id,v_result.event_type)
       is distinct from (p_athlete_id,v_injury_id,v_episode_id,v_type)
       or v_result.clinical_capture->>'request_hash' is distinct from v_meta->>'request_hash'
       or v_result.clinical_capture->>'recorder_id' is distinct from p_recorder_id::text then
      raise exception 'clinical_review_request_conflict' using errcode = '23514';
    end if;
    return v_result; -- A stable factual retry does not rebuild recording time.
  end if;
  if v_current is distinct from p_context then
    raise exception 'clinical_review_context_changed' using errcode = '23514';
  end if;
  if v_type = 'clinical_progression_review' then
    if v_current->'injury'->>'status' not in ('open','monitoring')
       or v_envelope->>'review_id' is distinct from v_identity::text
       or v_envelope->>'athlete_id' is distinct from p_athlete_id::text
       or v_envelope->>'injury_id' is distinct from v_injury_id::text
       or v_envelope->>'injury_episode_id' is distinct from v_episode_id::text
       or v_envelope->>'side' is distinct from v_current->'injury'->>'side'
       or v_envelope->>'side' not in ('left','right','bilateral')
       or coalesce(v_envelope->>'criterion_id','') = ''
       or coalesce(v_envelope->>'criterion_version','') !~ '^[1-9][0-9]*$'
       or jsonb_typeof(v_envelope->'criterion_version') is distinct from 'number'
       or jsonb_typeof(v_envelope->'interpretation') is distinct from 'object'
       or coalesce(v_envelope->>'profile_id','') = ''
       or coalesce(v_envelope->>'policy_hash','') !~ '^[a-f0-9]{64}$'
       or coalesce(v_envelope->>'policy_version','') !~ '^[1-9][0-9]*$'
       or jsonb_typeof(v_envelope->'policy_version') is distinct from 'number'
       or coalesce(v_envelope->>'decision','') not in ('approved','not_approved','deferred')
       or coalesce(v_meta->>'statement_reference','') = ''
       or coalesce(v_meta->>'statement_text','') = ''
       or lower(coalesce(v_envelope->'clinical_author'->>'author_id','')) in ('',p_recorder_id::text,p_athlete_id::text)
       or coalesce(v_envelope->'clinical_author'->>'display_name','') = ''
       or coalesce(v_envelope->'clinical_author'->>'qualification_reference','') = ''
       or jsonb_typeof(v_envelope->'clinical_author'->'clinical_scopes') is distinct from 'array'
       or jsonb_array_length(v_envelope->'clinical_author'->'clinical_scopes') = 0
       or jsonb_typeof(v_envelope->'evidence') is distinct from 'object'
       or coalesce(v_envelope->'evidence'->>'packet_revision','') !~ '^[a-f0-9]{64}$'
       or coalesce(v_envelope->'evidence'->>'safety_revision','') !~ '^[a-f0-9]{64}$'
       or jsonb_typeof(v_envelope->'evidence'->'references') is distinct from 'array'
       or coalesce(v_envelope->'evidence'->>'evidence_cutoff','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
       or coalesce(v_envelope->>'reviewed_at','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
       or (v_envelope->'evidence'->>'evidence_cutoff')::timestamptz > (v_envelope->>'reviewed_at')::timestamptz
       or (v_envelope->>'reviewed_at')::timestamptz < (v_current->'injury'->>'created_at')::timestamptz
       or (v_envelope->>'reviewed_at')::timestamptz > (v_provenance->>'confirmed_at')::timestamptz then
      raise exception 'invalid clinical review binding' using errcode = '23514';
    end if;
    select * into v_latest from public.injury_episode_events where athlete_id = p_athlete_id
      and injury_id = v_injury_id and injury_episode_id = v_episode_id and event_type = v_type
      and payload->>'criterion_id' = v_envelope->>'criterion_id' order by created_at desc,id desc limit 1;
    if v_envelope->>'supersedes_review_id' is distinct from v_latest.id::text
       or (v_latest.id is not null and (v_envelope->>'recorded_at')::timestamptz <=
           (v_latest.payload->>'recorded_at')::timestamptz)
       or (v_latest.id is null and p_supersession is not null)
       or (v_latest.id is not null and p_supersession is null) then
      raise exception 'clinical_review_replacement_conflict' using errcode = '23514';
    end if;
    if p_supersession is not null then
      if p_supersession->>'athlete_id' is distinct from p_athlete_id::text
         or p_supersession->>'injury_id' is distinct from v_injury_id::text
         or p_supersession->>'injury_episode_id' is distinct from v_episode_id::text
         or p_supersession->>'event_type' is distinct from 'clinical_progression_review_lifecycle'
         or p_supersession->'payload'->>'review_id' is distinct from v_latest.id::text
         or p_supersession->'payload'->>'replacement_review_id' is distinct from v_identity::text
         or p_supersession->'payload'->>'state' is distinct from 'superseded'
         or p_supersession->'payload'->>'lifecycle_id' is distinct from p_supersession->>'id'
         or p_supersession->'payload'->'provenance'->'recorder' is distinct from v_provenance->'recorder'
         or p_supersession->'payload'->'provenance'->'verifier' is distinct from v_provenance->'verifier'
         or p_supersession->'payload'->>'recorded_at' is distinct from v_envelope->>'recorded_at'
         or p_supersession->'payload'->>'effective_at' is distinct from v_envelope->>'recorded_at'
         or p_supersession->'clinical_capture'->>'policy' is distinct from v_meta->>'policy'
         or p_supersession->'clinical_capture'->>'recorder_id' is distinct from p_recorder_id::text
         or exists (select 1 from public.injury_episode_events where athlete_id = p_athlete_id
           and event_type = 'clinical_progression_review_lifecycle' and payload->>'review_id' = v_latest.id::text
           and payload->>'state' = 'superseded') then
        raise exception 'clinical_review_supersession_conflict' using errcode = '23514';
      end if;
    end if;
  else
    if p_supersession is not null or v_envelope->>'lifecycle_id' is distinct from v_identity::text
       or coalesce(v_envelope->>'state','') not in ('revoked','superseded') then
      raise exception 'invalid clinical lifecycle' using errcode = '22023';
    end if;
    v_old_id := v_envelope->>'review_id';
    select * into v_prior from public.injury_episode_events where id::text = v_old_id
      and athlete_id = p_athlete_id and injury_id = v_injury_id and injury_episode_id = v_episode_id
      and event_type = 'clinical_progression_review';
    if not found or coalesce(v_envelope->>'effective_at','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
       or (v_envelope->>'effective_at')::timestamptz < (v_prior.payload->>'recorded_at')::timestamptz
       or (v_envelope->>'effective_at')::timestamptz > (v_provenance->>'confirmed_at')::timestamptz then
      raise exception 'clinical_lifecycle_scope_or_time_changed' using errcode = '23514';
    end if;
    if v_envelope->>'state' = 'superseded' then
      select * into v_replacement from public.injury_episode_events where id::text = v_envelope->>'replacement_review_id'
        and athlete_id = p_athlete_id and injury_id = v_injury_id and injury_episode_id = v_episode_id
        and event_type = 'clinical_progression_review' and payload->>'supersedes_review_id' = v_old_id
        and payload->>'criterion_id' = v_prior.payload->>'criterion_id';
      if not found or v_replacement.id = v_prior.id then
        raise exception 'clinical_lifecycle_replacement_invalid' using errcode = '23514';
      end if;
    elsif v_envelope->>'replacement_review_id' is not null then
      raise exception 'revocation_cannot_replace' using errcode = '23514';
    end if;
  end if;
  insert into public.injury_episode_events(id,athlete_id,injury_id,injury_episode_id,event_type,payload,clinical_capture,created_at)
    values(v_identity,p_athlete_id,v_injury_id,v_episode_id,v_type,v_envelope,v_meta,(v_envelope->>'recorded_at')::timestamptz)
    returning * into v_result;
  if p_supersession is not null then
    insert into public.injury_episode_events(id,athlete_id,injury_id,injury_episode_id,event_type,payload,clinical_capture,created_at)
      values((p_supersession->>'id')::uuid,p_athlete_id,v_injury_id,v_episode_id,'clinical_progression_review_lifecycle',
        p_supersession->'payload',p_supersession->'clinical_capture',(v_envelope->>'recorded_at')::timestamptz);
  end if;
  return v_result;
end;
$$;
revoke all on function public.record_clinical_review_event(uuid,uuid,jsonb,jsonb,jsonb) from public, anon, authenticated;
grant execute on function public.record_clinical_review_event(uuid,uuid,jsonb,jsonb,jsonb) to service_role;

-- Pin check supplements (rather than replaces) the existing acceptance trigger.
-- Started continuation may stop under a hold; completed history is never replayed.
create or replace function public.verify_frozen_clinical_review()
returns trigger language plpgsql security definer set search_path = public, pg_temp as $$
declare
  v_block jsonb;
  v_pin jsonb;
  v_review public.injury_episode_events%rowtype;
begin
  if new.prescription_snapshot is null or new.status not in ('started','done','modified') then return new; end if;
  if tg_op = 'UPDATE' and (old.status in ('done','modified') or
    (old.status = 'started' and new.rehab_performance = 'stopped')) then return new; end if;
  perform pg_advisory_xact_lock(hashtextextended('injury:' || new.athlete_id::text, 0));
  for v_block in select b from jsonb_array_elements(new.prescription_snapshot->'session'->'blocks') b
      where b ? 'clinical_review_pin' loop
    v_pin := v_block->'clinical_review_pin';
    select * into v_review from public.injury_episode_events where id::text = v_pin->>'review_id'
      and athlete_id = new.athlete_id and injury_id::text = v_block->>'injury_id'
      and injury_episode_id::text = v_block->>'injury_episode_id' and event_type = 'clinical_progression_review';
    if not found or v_review.payload->>'decision' is distinct from 'approved'
       or (v_review.payload->>'valid_until' is not null and
          (v_review.payload->>'valid_until')::timestamptz <= clock_timestamp())
       or v_pin->>'criterion_id' is distinct from v_review.payload->>'criterion_id'
       or v_pin->'criterion_version' is distinct from v_review.payload->'criterion_version'
       or v_pin->>'option_id' is distinct from v_review.payload->'selected_prescription'->>'option_id'
       or v_pin->'option_version' is distinct from v_review.payload->'selected_prescription'->'option_version'
       or v_pin->'selection_version' is distinct from v_review.payload->'selected_prescription'->'selection_version'
       or v_pin->>'materialised_prescription_hash' is distinct from
          v_review.payload->'selected_prescription'->>'materialised_prescription_hash'
       or coalesce(v_pin->>'materialised_prescription_hash','') !~ '^[a-f0-9]{64}$'
       or new.prescription_snapshot->'evidence_context'->>'exposure_id' is distinct from
          (select id::text from public.rehab_exposures where athlete_id = new.athlete_id order by created_at desc,id desc limit 1)
       or new.prescription_snapshot->'evidence_context'->>'event_id' is distinct from
         (select id::text from public.injury_episode_events where athlete_id = new.athlete_id
          and event_type in ('injury_checkin','delayed_rehab_response','clinician_clearance_report',
            'rehab_progression_assessment','clinical_progression_review','clinical_progression_review_lifecycle')
          order by created_at desc,id desc limit 1)
       or exists (select 1 from public.injury_episode_events where athlete_id = new.athlete_id
          and injury_id = v_review.injury_id and injury_episode_id = v_review.injury_episode_id
          and event_type = 'clinical_progression_review_lifecycle' and payload->>'review_id' = v_review.id::text)
       or not exists (select 1 from public.injury_flags where id = v_review.injury_id and athlete_id = new.athlete_id
          and episode_id = v_review.injury_episode_id and status in ('open','monitoring')
          and exists (select 1 from jsonb_array_elements(new.prescription_snapshot->'injury_context') c
            where c->>'id' = id::text and c->>'episode_id' = episode_id::text
              and (c->>'updated_at')::timestamptz is not distinct from updated_at)) then
      raise exception 'clinical_review_pin_invalidated_hold' using errcode = '23514';
    end if;
  end loop;
  return new;
end;
$$;
drop trigger if exists verify_frozen_clinical_review on public.session_completions;
create trigger verify_frozen_clinical_review before insert or update on public.session_completions
  for each row execute function public.verify_frozen_clinical_review();
revoke all on function public.verify_frozen_clinical_review() from public, anon, authenticated, service_role;

-- Preserve the existing bundle/allocation guard; extend only freshness sources
-- and recheck saved work that has not started.
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
       and exists (select 1 from jsonb_array_elements(old.prescription_snapshot->'session'->'blocks') b
                   where b ? 'policy_id' or b ? 'clinical_review_pin') then
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
    if tg_op = 'INSERT' or old.prescription_snapshot is null or old.status not in ('started','done','modified') then
      perform pg_advisory_xact_lock(hashtextextended('injury:' || new.athlete_id::text, 0));
      if new.prescription_snapshot->'evidence_context'->>'exposure_id' is distinct from
         (select id::text from public.rehab_exposures where athlete_id = new.athlete_id order by created_at desc, id desc limit 1)
         or new.prescription_snapshot->'evidence_context'->>'event_id' is distinct from
         (select id::text from public.injury_episode_events where athlete_id = new.athlete_id
           and event_type in ('injury_checkin','delayed_rehab_response','clinician_clearance_report',
             'rehab_progression_assessment','clinical_progression_review','clinical_progression_review_lifecycle') order by created_at desc, id desc limit 1) then
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
      -- Server-owned bundle identity groups drills without grouping legacy blocks.
      select count(distinct (s.id, coalesce(nullif(b->>'rehab_allocation_id', ''),
                                           'block:' || ordinal::text)))
        into v_used from public.session_completions s,
        lateral jsonb_array_elements(s.prescription_snapshot->'session'->'blocks')
          with ordinality as items(b, ordinal)
        where s.athlete_id = new.athlete_id and s.training_day = new.training_day
          and s.status in ('started','done','modified') and s.id <> new.id and b->>'block_type' = 'rehab';
      if exists (select 1 from jsonb_array_elements(new.prescription_snapshot->'session'->'blocks') b where b->>'block_type' = 'rehab')
         and v_used + (select count(distinct coalesce(nullif(b->>'rehab_allocation_id', ''),
                                                     'block:' || ordinal::text))
                       from jsonb_array_elements(new.prescription_snapshot->'session'->'blocks')
                         with ordinality as items(b, ordinal)
                       where b->>'block_type' = 'rehab') > v_limit then
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
