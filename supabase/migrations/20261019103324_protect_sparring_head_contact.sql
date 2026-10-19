-- Sparring reports can be reopened from History and corrected later
-- (POST /api/today/sparring-log with a higher detail_revision).
--
-- A correction may fix rounds, intensity and notes, but recorded head-impact
-- evidence stays protected: head_contact can only rise (none < light < heavy),
-- and rocked is still never withdrawn, so a safety hold and its admin review
-- cannot be erased retrospectively. Otherwise identical to
-- 20261019014437_link_sparring_detail_to_manual_sessions.sql.
--
-- Repeatable: the function is replaced in place.

create or replace function public.record_sparring_log(
  p_athlete_id uuid,
  p_log jsonb,
  p_review_reason text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_log public.sparring_logs%rowtype;
  v_review public.admin_reviews%rowtype;
  v_rocked boolean := coalesce((p_log->>'rocked')::boolean, false);
  v_request uuid := nullif(p_log->>'client_request_id', '')::uuid;
  v_external uuid := nullif(p_log->>'external_session_id', '')::uuid;
  v_revision integer := greatest(coalesce(nullif(p_log->>'detail_revision', '')::integer, 0), 0);
  v_day date := (p_log->>'training_day')::date;
  v_was_rocked boolean := false;
  v_replayed_log uuid;
begin
  if v_rocked and coalesce(btrim(p_review_reason), '') = '' then
    raise exception 'record_sparring_log: rocked report requires a review reason'
      using errcode = '22023';
  end if;

  if v_request is not null then
    -- Concurrent copies of one request queue here until the first commits, so
    -- exactly one of them writes and the rest are answered from the history.
    perform pg_advisory_xact_lock(hashtextextended(p_athlete_id::text || ':' || v_request::text, 0));
    select sparring_log_id into v_replayed_log from public.sparring_log_requests
      where athlete_id = p_athlete_id and client_request_id = v_request;
    if found then
      select * into v_log from public.sparring_logs where id = v_replayed_log;
      if v_log.admin_review_id is not null then
        select * into v_review from public.admin_reviews where id = v_log.admin_review_id;
      end if;
      return jsonb_build_object(
        'log', to_jsonb(v_log),
        'review', case when v_review.id is not null then to_jsonb(v_review) else null end,
        'replayed', true
      );
    end if;
  end if;

  if v_external is not null then
    -- The manual session owns the training day: contact is never re-dated.
    select training_day into v_day from public.external_training_sessions
      where id = v_external and athlete_id = p_athlete_id
        and deleted_at is null and activity = 'sparring'
      for share;
    if not found then
      raise exception 'record_sparring_log: sparring session not found'
        using errcode = 'P0002';
    end if;
  end if;

  insert into public.sparring_logs (
    athlete_id, plan_id, session_id, training_day, source, planned_intensity,
    intensity, rounds_completed, round_seconds, head_contact, rocked, notes,
    external_session_id, detail_revision
  ) values (
    p_athlete_id,
    nullif(p_log->>'plan_id', '')::uuid,
    nullif(p_log->>'session_id', ''),
    v_day,
    p_log->>'source',
    nullif(p_log->>'planned_intensity', ''),
    p_log->>'intensity',
    (p_log->>'rounds_completed')::integer,
    nullif(p_log->>'round_seconds', '')::integer,
    p_log->>'head_contact',
    v_rocked,
    coalesce(p_log->>'notes', ''),
    v_external,
    v_revision
  )
  on conflict (external_session_id) where external_session_id is not null do nothing
  returning * into v_log;

  if not found then
    -- Another report for the same manual session. A newer revision corrects
    -- the details in place; an older one that arrived late changes nothing
    -- but can still add a head-impact report, which is never withdrawn.
    select * into v_log from public.sparring_logs
      where external_session_id = v_external for update;
    v_was_rocked := v_log.rocked;
    if v_revision > v_log.detail_revision then
      update public.sparring_logs set
        intensity = p_log->>'intensity',
        rounds_completed = (p_log->>'rounds_completed')::integer,
        round_seconds = nullif(p_log->>'round_seconds', '')::integer,
        -- Recorded head contact is safety evidence: a correction can raise
        -- it but never lowers it (none < light < heavy).
        head_contact = case
          when array_position(array['none','light','heavy'], p_log->>'head_contact')
             < array_position(array['none','light','heavy'], v_log.head_contact)
          then v_log.head_contact
          else p_log->>'head_contact'
        end,
        rocked = v_log.rocked or v_rocked,
        notes = coalesce(p_log->>'notes', ''),
        detail_revision = v_revision
      where id = v_log.id
      returning * into v_log;
    elsif v_rocked and not v_log.rocked then
      update public.sparring_logs set rocked = true
      where id = v_log.id
      returning * into v_log;
    end if;
  end if;

  if v_rocked and not v_was_rocked then
    insert into public.admin_reviews (athlete_id, reason, status)
    values (p_athlete_id, p_review_reason, 'pending')
    returning * into v_review;
    update public.sparring_logs set admin_review_id = v_review.id
      where id = v_log.id
      returning * into v_log;
  elsif v_log.admin_review_id is not null then
    select * into v_review from public.admin_reviews where id = v_log.admin_review_id;
  end if;

  if v_request is not null then
    insert into public.sparring_log_requests (athlete_id, client_request_id, sparring_log_id)
    values (p_athlete_id, v_request, v_log.id);
  end if;

  return jsonb_build_object(
    'log', to_jsonb(v_log),
    'review', case when v_review.id is not null then to_jsonb(v_review) else null end,
    'replayed', false
  );
end;
$$;

revoke all on function public.record_sparring_log(uuid, jsonb, text) from public, anon, authenticated;
grant execute on function public.record_sparring_log(uuid, jsonb, text) to service_role;
