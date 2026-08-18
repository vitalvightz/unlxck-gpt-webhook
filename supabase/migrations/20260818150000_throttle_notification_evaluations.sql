-- Keep state-aware notification diagnostics useful without updating the same
-- unchanged evaluation row on every ten-minute worker sweep.

drop function if exists public.record_notification_evaluation(
  uuid, date, text, text, text, timestamptz, timestamptz, text, text,
  boolean, text, text[], integer, text, text, jsonb, uuid, text
);

create or replace function public.record_notification_evaluation(
  p_profile_id uuid,
  p_training_day date,
  p_intent text,
  p_notification_type text,
  p_category text,
  p_evaluated_at timestamptz,
  p_scheduled_for timestamptz,
  p_timing_source text,
  p_timing_confidence text,
  p_eligible boolean,
  p_decision text,
  p_rejection_reasons text[],
  p_priority integer,
  p_dedupe_key text,
  p_variant_id text,
  p_source_event_metadata jsonb,
  p_resulting_delivery_id uuid,
  p_evaluation_key text,
  p_min_interval_seconds integer default 0
)
returns public.notification_evaluations
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.notification_evaluations;
begin
  insert into public.notification_evaluations (
    profile_id, training_day, intent, notification_type, category,
    evaluated_at, first_evaluated_at, last_evaluated_at, scheduled_for,
    timing_source, timing_confidence, eligible, decision, rejection_reasons,
    priority, dedupe_key, variant_id, source_event_metadata,
    resulting_delivery_id, evaluation_key
  ) values (
    p_profile_id, p_training_day, p_intent, nullif(p_notification_type, ''),
    nullif(p_category, ''), p_evaluated_at, p_evaluated_at, p_evaluated_at,
    p_scheduled_for, nullif(p_timing_source, ''), nullif(p_timing_confidence, ''),
    p_eligible, p_decision, coalesce(p_rejection_reasons, '{}'::text[]),
    p_priority, nullif(p_dedupe_key, ''), nullif(p_variant_id, ''),
    coalesce(p_source_event_metadata, '{}'::jsonb), p_resulting_delivery_id,
    p_evaluation_key
  )
  on conflict (profile_id, evaluation_key) do update
  set evaluated_at = excluded.evaluated_at,
      last_evaluated_at = excluded.evaluated_at,
      evaluation_count = public.notification_evaluations.evaluation_count + 1,
      eligible = excluded.eligible,
      decision = excluded.decision,
      rejection_reasons = excluded.rejection_reasons,
      resulting_delivery_id = coalesce(
        excluded.resulting_delivery_id,
        public.notification_evaluations.resulting_delivery_id
      ),
      source_event_metadata = excluded.source_event_metadata,
      updated_at = timezone('utc', now())
  where p_min_interval_seconds <= 0
     or public.notification_evaluations.last_evaluated_at
        <= excluded.evaluated_at - make_interval(secs => p_min_interval_seconds)
  returning * into v_row;

  if v_row is null then
    select * into v_row
    from public.notification_evaluations
    where profile_id = p_profile_id and evaluation_key = p_evaluation_key;
  end if;
  return v_row;
end;
$$;

revoke all on function public.record_notification_evaluation(
  uuid, date, text, text, text, timestamptz, timestamptz, text, text,
  boolean, text, text[], integer, text, text, jsonb, uuid, text, integer
) from public, anon, authenticated;
grant execute on function public.record_notification_evaluation(
  uuid, date, text, text, text, timestamptz, timestamptz, text, text,
  boolean, text, text[], integer, text, text, jsonb, uuid, text, integer
) to service_role;
