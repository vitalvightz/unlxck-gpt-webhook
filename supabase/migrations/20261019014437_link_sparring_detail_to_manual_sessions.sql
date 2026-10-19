-- Detailed post-sparring follow-up for manually logged sparring, and retry-safe
-- writes for every sparring report (api/routes/today.py POST /api/today/sparring-log).
--
-- external_training_sessions remains the record of the training occurrence and
-- its workload. A linked sparring_logs row only adds that occurrence's contact
-- and safety evidence, so one manual session has at most one detail row. The
-- composite key keeps the link inside the athlete's own records. Soft-deleting
-- the manual session keeps its safety evidence; a hard delete unlinks it.
--
-- sparring_log_requests is the append-only history of every accepted request
-- id. A retried request (lost response, double tap, delayed duplicate) is
-- answered from it and never writes again, even after a later correction.
-- detail_revision orders corrections from one report: an older revision that
-- arrives late cannot overwrite a newer one. admin_review_id records the
-- review a rocked report opened, so a retry returns it without opening another.
--
-- Repeatable: every step is guarded, and the function is replaced in place.

alter table public.sparring_logs
  add column if not exists external_session_id uuid,
  add column if not exists detail_revision integer not null default 0,
  add column if not exists admin_review_id uuid references public.admin_reviews(id) on delete set null;

-- The foreign key depends on the composite key, so both are added only when
-- missing rather than dropped and recreated.
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'external_training_sessions_id_athlete_key'
      and conrelid = 'public.external_training_sessions'::regclass) then
    alter table public.external_training_sessions
      add constraint external_training_sessions_id_athlete_key unique (id, athlete_id);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'sparring_logs_external_session_fkey'
      and conrelid = 'public.sparring_logs'::regclass) then
    alter table public.sparring_logs
      add constraint sparring_logs_external_session_fkey
      foreign key (external_session_id, athlete_id)
      references public.external_training_sessions(id, athlete_id)
      on delete set null (external_session_id);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'sparring_logs_detail_revision_check'
      and conrelid = 'public.sparring_logs'::regclass) then
    alter table public.sparring_logs
      add constraint sparring_logs_detail_revision_check check (detail_revision >= 0);
  end if;
end
$$;

create unique index if not exists sparring_logs_external_session_key
  on public.sparring_logs (external_session_id) where external_session_id is not null;

create table if not exists public.sparring_log_requests (
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  client_request_id uuid not null,
  sparring_log_id uuid not null references public.sparring_logs(id) on delete cascade,
  created_at timestamptz not null default now(),
  constraint sparring_log_requests_pkey primary key (athlete_id, client_request_id)
);
create index if not exists sparring_log_requests_log_idx on public.sparring_log_requests (sparring_log_id);

-- Backend-only bookkeeping: no client access at all.
alter table public.sparring_log_requests enable row level security;
revoke all on public.sparring_log_requests from public, anon, authenticated;
grant all on public.sparring_log_requests to service_role;

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
        head_contact = p_log->>'head_contact',
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
