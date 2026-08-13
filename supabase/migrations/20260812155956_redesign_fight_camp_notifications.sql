-- Fight-camp notification orchestration: auditable evaluations, deterministic
-- templates, action invalidation, and atomic class-aware delivery claiming.

comment on column public.notification_preferences.preferred_training_time is
  'Optional athlete-local preference. Null enables auditable schedule/history/fallback inference.';

alter table public.notification_deliveries
  add column if not exists intent text,
  add column if not exists training_day date,
  add column if not exists scheduled_for timestamptz,
  add column if not exists timing_source text,
  add column if not exists timing_confidence text,
  add column if not exists variant_id text,
  add column if not exists source_event_metadata jsonb not null default '{}'::jsonb,
  add column if not exists action_key text,
  add column if not exists notification_class text not null default 'routine',
  add column if not exists respect_quiet_hours boolean not null default true,
  add column if not exists merged_intents text[] not null default '{}'::text[],
  add column if not exists cancelled_at timestamptz,
  add column if not exists cancellation_reason text;

update public.notification_deliveries
set intent = notification_type
where intent is null;

alter table public.notification_deliveries
  alter column intent set not null;

alter table public.notification_deliveries
  drop constraint if exists notification_deliveries_status_check;
alter table public.notification_deliveries
  add constraint notification_deliveries_status_check
  check (status in ('pending', 'sent', 'partial', 'failed', 'cancelled'));

alter table public.notification_deliveries
  drop constraint if exists notification_deliveries_timing_confidence_check;
alter table public.notification_deliveries
  add constraint notification_deliveries_timing_confidence_check
  check (timing_confidence is null or timing_confidence in ('high', 'medium', 'low'));

alter table public.notification_deliveries
  drop constraint if exists notification_deliveries_class_check;
alter table public.notification_deliveries
  add constraint notification_deliveries_class_check
  check (notification_class in ('routine', 'safety', 'event'));

create index if not exists notification_deliveries_profile_day_class_idx
  on public.notification_deliveries (profile_id, training_day, notification_class, claimed_at desc);
create index if not exists notification_deliveries_profile_intent_variant_idx
  on public.notification_deliveries (profile_id, intent, sent_at desc)
  where status in ('sent', 'partial');
create index if not exists notification_deliveries_profile_action_idx
  on public.notification_deliveries (profile_id, action_key, training_day)
  where action_key is not null and status in ('pending', 'failed');

create table if not exists public.notification_templates (
  intent text not null,
  variant_id text not null,
  title_template text not null
    constraint notification_templates_title_length check (char_length(title_template) between 1 and 40),
  body_template text not null
    constraint notification_templates_body_length check (char_length(body_template) between 1 and 90),
  locale text not null default 'en-GB',
  template_version integer not null default 1 check (template_version > 0),
  active boolean not null default true,
  selection_weight integer not null default 1 check (selection_weight between 1 and 100),
  minimum_timing_confidence text not null default 'low'
    check (minimum_timing_confidence in ('low', 'medium', 'high')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  primary key (intent, variant_id, locale, template_version)
);

create table if not exists public.notification_action_states (
  profile_id uuid not null references public.profiles(id) on delete cascade,
  action_key text not null,
  training_day date not null,
  completed_at timestamptz not null default timezone('utc', now()),
  source_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  primary key (profile_id, action_key, training_day)
);

create table if not exists public.notification_evaluations (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  training_day date not null,
  intent text not null,
  notification_type text,
  category text,
  evaluated_at timestamptz not null default timezone('utc', now()),
  first_evaluated_at timestamptz not null default timezone('utc', now()),
  last_evaluated_at timestamptz not null default timezone('utc', now()),
  evaluation_count integer not null default 1 check (evaluation_count > 0),
  scheduled_for timestamptz,
  timing_source text,
  timing_confidence text check (timing_confidence is null or timing_confidence in ('high', 'medium', 'low')),
  eligible boolean not null default false,
  decision text not null,
  rejection_reasons text[] not null default '{}'::text[],
  priority smallint check (priority is null or priority between 1 and 100),
  dedupe_key text,
  variant_id text,
  source_event_metadata jsonb not null default '{}'::jsonb,
  resulting_delivery_id uuid references public.notification_deliveries(id) on delete set null,
  evaluation_key text not null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint notification_evaluations_profile_key unique (profile_id, evaluation_key)
);

create index if not exists notification_evaluations_diagnostic_idx
  on public.notification_evaluations (profile_id, training_day, intent, last_evaluated_at desc);
create index if not exists notification_evaluations_delivery_idx
  on public.notification_evaluations (resulting_delivery_id)
  where resulting_delivery_id is not null;

alter table public.notification_templates enable row level security;
alter table public.notification_action_states enable row level security;
alter table public.notification_evaluations enable row level security;

revoke all on public.notification_templates from public, anon, authenticated;
revoke all on public.notification_action_states from public, anon, authenticated;
revoke all on public.notification_evaluations from public, anon, authenticated;
grant all on public.notification_templates to service_role;
grant all on public.notification_action_states to service_role;
grant all on public.notification_evaluations to service_role;

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
  p_evaluation_key text
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
  returning * into v_row;
  return v_row;
end;
$$;

create or replace function public.claim_notification_delivery_v2(
  p_profile_id uuid,
  p_notification_type text,
  p_intent text,
  p_category text,
  p_priority integer,
  p_title text,
  p_body text,
  p_url text,
  p_tag text,
  p_dedupe_key text,
  p_expires_at timestamptz,
  p_training_day date,
  p_scheduled_for timestamptz,
  p_timing_source text,
  p_timing_confidence text,
  p_variant_id text,
  p_source_event_metadata jsonb,
  p_action_key text,
  p_notification_class text,
  p_respect_quiet_hours boolean,
  p_merged_intents text[],
  p_daily_cap integer,
  p_min_spacing_minutes integer
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_now timestamptz := timezone('utc', now());
  v_existing public.notification_deliveries;
  v_delivery public.notification_deliveries;
  v_count integer;
  v_last_at timestamptz;
  v_claim_token uuid := gen_random_uuid();
begin
  perform pg_advisory_xact_lock(
    hashtext('notification_delivery_v2'),
    hashtext(p_profile_id::text || ':' || coalesce(p_training_day::text, 'none'))
  );

  if p_expires_at <= v_now then
    return jsonb_build_object('decision', 'outside_due_window');
  end if;

  if p_action_key is not null and exists (
    select 1 from public.notification_action_states
    where profile_id = p_profile_id
      and action_key = p_action_key
      and training_day = p_training_day
  ) then
    return jsonb_build_object('decision', 'user_action_already_done');
  end if;

  select * into v_existing
  from public.notification_deliveries
  where profile_id = p_profile_id and dedupe_key = p_dedupe_key
  for update;

  if found then
    if v_existing.attempt_count < 3 and (
      v_existing.status = 'failed'
      or (v_existing.status = 'pending' and v_existing.claimed_at <= v_now - interval '15 minutes')
    ) then
      update public.notification_deliveries
      set notification_type = p_notification_type,
          intent = p_intent,
          category = p_category,
          priority = p_priority,
          title = p_title,
          body = p_body,
          url = p_url,
          tag = p_tag,
          expires_at = p_expires_at,
          training_day = p_training_day,
          scheduled_for = p_scheduled_for,
          timing_source = nullif(p_timing_source, ''),
          timing_confidence = nullif(p_timing_confidence, ''),
          variant_id = nullif(p_variant_id, ''),
          source_event_metadata = coalesce(p_source_event_metadata, '{}'::jsonb),
          action_key = nullif(p_action_key, ''),
          notification_class = p_notification_class,
          respect_quiet_hours = p_respect_quiet_hours,
          merged_intents = coalesce(p_merged_intents, '{}'::text[]),
          status = 'pending', claim_token = v_claim_token, claimed_at = v_now,
          attempt_count = attempt_count + 1, delivered_count = 0,
          error_code = null, sent_at = null, cancelled_at = null,
          cancellation_reason = null
      where id = v_existing.id
      returning * into v_delivery;
      return jsonb_build_object('decision', 'claimed', 'delivery', to_jsonb(v_delivery));
    end if;
    return jsonb_build_object('decision', 'duplicate_dedupe_key');
  end if;

  select count(*) into v_count
  from public.notification_deliveries
  where profile_id = p_profile_id
    and training_day = p_training_day
    and notification_class = p_notification_class
    and status in ('pending', 'sent', 'partial');
  if v_count >= greatest(1, p_daily_cap) then
    return jsonb_build_object('decision', 'daily_cap');
  end if;

  if p_min_spacing_minutes > 0 then
    select max(coalesce(sent_at, claimed_at)) into v_last_at
    from public.notification_deliveries
    where profile_id = p_profile_id
      and training_day = p_training_day
      and notification_class = p_notification_class
      and status in ('pending', 'sent', 'partial');
    if v_last_at is not null
       and v_last_at > v_now - make_interval(mins => p_min_spacing_minutes) then
      return jsonb_build_object('decision', 'cooldown_active');
    end if;
  end if;

  insert into public.notification_deliveries (
    profile_id, notification_type, intent, category, priority, title, body,
    url, tag, dedupe_key, expires_at, training_day, scheduled_for,
    timing_source, timing_confidence, variant_id, source_event_metadata,
    action_key, notification_class, respect_quiet_hours, merged_intents,
    status, claim_token, claimed_at, attempt_count
  ) values (
    p_profile_id, p_notification_type, p_intent, p_category, p_priority,
    p_title, p_body, p_url, p_tag, p_dedupe_key, p_expires_at,
    p_training_day, p_scheduled_for, nullif(p_timing_source, ''),
    nullif(p_timing_confidence, ''), nullif(p_variant_id, ''),
    coalesce(p_source_event_metadata, '{}'::jsonb), nullif(p_action_key, ''),
    p_notification_class, p_respect_quiet_hours,
    coalesce(p_merged_intents, '{}'::text[]), 'pending', v_claim_token,
    v_now, 1
  ) returning * into v_delivery;

  return jsonb_build_object('decision', 'claimed', 'delivery', to_jsonb(v_delivery));
end;
$$;

create or replace function public.invalidate_notification_action(
  p_profile_id uuid,
  p_action_key text,
  p_training_day date,
  p_completed_at timestamptz,
  p_source_metadata jsonb default '{}'::jsonb
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  v_cancelled integer;
begin
  insert into public.notification_action_states (
    profile_id, action_key, training_day, completed_at, source_metadata
  ) values (
    p_profile_id, p_action_key, p_training_day, p_completed_at,
    coalesce(p_source_metadata, '{}'::jsonb)
  )
  on conflict (profile_id, action_key, training_day) do update
  set completed_at = greatest(
        public.notification_action_states.completed_at,
        excluded.completed_at
      ),
      source_metadata = excluded.source_metadata,
      updated_at = timezone('utc', now());

  update public.notification_deliveries
  set status = 'cancelled', cancelled_at = p_completed_at,
      cancellation_reason = 'user_action_already_done'
  where profile_id = p_profile_id
    and action_key = p_action_key
    and training_day = p_training_day
    and status in ('pending', 'failed');
  get diagnostics v_cancelled = row_count;
  return v_cancelled;
end;
$$;

revoke all on function public.record_notification_evaluation(
  uuid, date, text, text, text, timestamptz, timestamptz, text, text,
  boolean, text, text[], integer, text, text, jsonb, uuid, text
) from public, anon, authenticated;
grant execute on function public.record_notification_evaluation(
  uuid, date, text, text, text, timestamptz, timestamptz, text, text,
  boolean, text, text[], integer, text, text, jsonb, uuid, text
) to service_role;

revoke all on function public.claim_notification_delivery_v2(
  uuid, text, text, text, integer, text, text, text, text, text, timestamptz,
  date, timestamptz, text, text, text, jsonb, text, text, boolean, text[], integer, integer
) from public, anon, authenticated;
grant execute on function public.claim_notification_delivery_v2(
  uuid, text, text, text, integer, text, text, text, text, text, timestamptz,
  date, timestamptz, text, text, text, jsonb, text, text, boolean, text[], integer, integer
) to service_role;

revoke all on function public.invalidate_notification_action(
  uuid, text, date, timestamptz, jsonb
) from public, anon, authenticated;
grant execute on function public.invalidate_notification_action(
  uuid, text, date, timestamptz, jsonb
) to service_role;

insert into public.notification_templates (
  intent, variant_id, title_template, body_template, locale, template_version,
  active, selection_weight
) values
  ('morning_readiness', 'mr-01', 'CAMP CHECK. REPORT IN.', 'Sleep, body, pain. Give me the read before we set today''s work.', 'en-GB', 1, true, 1),
  ('morning_readiness', 'mr-02', 'MORNING CHECK. YOUR READ.', 'Tell me how you slept, how you feel and what hurts before we train.', 'en-GB', 1, true, 1),
  ('morning_readiness', 'mr-03', 'SET TODAY''S CALL.', 'Check in now. Your sleep, body and pain decide how we attack today.', 'en-GB', 1, true, 1),
  ('morning_readiness', 'mr-04', 'CAMP STARTS WITH THE READ.', 'Report sleep, body and pain. Then we set the work.', 'en-GB', 1, true, 1),
  ('morning_readiness', 'mr-05', 'BODY FIRST. TRAINING SECOND.', 'Give me sleep, readiness and pain before today''s work gets the green light.', 'en-GB', 1, true, 1),
  ('morning_readiness', 'mr-06', 'THE WORK STARTS WITH HONESTY.', 'Report how you woke up. We train the body that is here, not the plan on paper.', 'en-GB', 1, true, 1),
  ('morning_readiness', 'mr-07', 'EARN THE RIGHT CALL.', 'Check in before {session}. Set the right call.', 'en-GB', 1, true, 1),
  ('morning_readiness', 'mr-08', 'READ THE BODY. SET THE DAY.', 'Sleep, soreness, pain. Give me the facts and I''ll set the call.', 'en-GB', 1, true, 1),
  ('missed_checkin', 'mc-01', 'CHECK-IN STILL OPEN.', 'Give me the read so today''s call matches the athlete who showed up.', 'en-GB', 1, true, 1),
  ('missed_checkin', 'mc-02', 'REPORT IN BEFORE TRAINING.', 'Sleep, body and pain are still missing. Check in before the work starts.', 'en-GB', 1, true, 1),
  ('missed_checkin', 'mc-03', 'I STILL NEED YOUR READ.', 'Open Today and check in before we lock the session call.', 'en-GB', 1, true, 1),
  ('missed_checkin', 'mc-04', 'DON''T TRAIN BLIND.', 'Check in now so today''s load reflects how you actually feel.', 'en-GB', 1, true, 1),
  ('missed_checkin', 'mc-05', 'THE SESSION NEEDS YOUR READ.', '{session} still needs your read. Check in now.', 'en-GB', 1, true, 1),
  ('missed_checkin', 'mc-06', 'NO READ. NO CLEAN CALL.', 'Report before {session}. Match the load to today.', 'en-GB', 1, true, 1),
  ('daily_camp_briefing', 'db-01', 'TODAY''S WORK IS LXCKED.', '{session}. Keep the rest of the day pointed at it.', 'en-GB', 1, true, 1),
  ('daily_camp_briefing', 'db-02', 'TODAY HAS A JOB.', '{session}. Keep the day clean around that job.', 'en-GB', 1, true, 1),
  ('daily_camp_briefing', 'db-03', 'CAMP BRIEFING.', '{session}. The priority. Everything else supports.', 'en-GB', 1, true, 1),
  ('daily_camp_briefing', 'db-04', 'TODAY''S CALL IS SET.', '{session}. Open Today for the full brief.', 'en-GB', 1, true, 1),
  ('daily_camp_briefing', 'db-05', 'ONE TARGET. EXECUTE IT.', '{session}. Keep the work sharp and the noise out.', 'en-GB', 1, true, 1),
  ('daily_camp_briefing', 'db-06', 'THE DAY HAS A CENTRE.', '{session}. Build the rest of today around that job.', 'en-GB', 1, true, 1),
  ('daily_camp_briefing', 'db-07', 'KNOW THE ASSIGNMENT.', 'Priority: {session}. Open the brief. Execute clean.', 'en-GB', 1, true, 1),
  ('daily_camp_briefing', 'db-08', 'CAMP MOVES TODAY.', '{session}. This moves the camp forward.', 'en-GB', 1, true, 1),
  ('session_preparation', 'sp-01', 'GET READY FOR THE WORK.', 'Fuel and hydrate for {session}. Training is later.', 'en-GB', 1, true, 1),
  ('session_preparation', 'sp-02', 'PREP STARTS NOW.', 'Eat, drink and clear the noise before {session}.', 'en-GB', 1, true, 1),
  ('session_preparation', 'sp-03', 'POINT THE DAY AT TRAINING.', 'Fuel and hydrate. {session} is the next job.', 'en-GB', 1, true, 1),
  ('session_preparation', 'sp-04', 'BUILD INTO THE SESSION.', 'Get fuel, fluids and focus in place for {session}.', 'en-GB', 1, true, 1),
  ('session_preparation', 'sp-05', 'FUEL THE NEXT ROUND.', 'Get food and fluids in. {session} needs a ready athlete.', 'en-GB', 1, true, 1),
  ('session_preparation', 'sp-06', 'CLEAR THE RUNWAY.', 'Hydrate, eat and cut the noise before {session}.', 'en-GB', 1, true, 1),
  ('session_preparation', 'sp-07', 'PREP LIKE IT COUNTS.', 'Set the body and the head for {session}. No rushed start.', 'en-GB', 1, true, 1),
  ('session_preparation', 'sp-08', 'ARRIVE READY.', '{session} starts now: fuel, hydrate, focus.', 'en-GB', 1, true, 1),
  ('session_near', 'sn-01', '30 MINUTES. SWITCH ON.', 'Open today''s call before you put the work in.', 'en-GB', 1, true, 1),
  ('session_near', 'sn-02', 'THE SESSION IS CLOSE.', 'Get changed, get warm and open the final call.', 'en-GB', 1, true, 1),
  ('session_near', 'sn-03', 'TIME TO LOCK IN.', 'Training is close. Open Today and take the session in clean.', 'en-GB', 1, true, 1),
  ('session_near', 'sn-04', 'NEXT JOB: TRAIN.', 'Finish the prep and open the session before you start.', 'en-GB', 1, true, 1),
  ('session_near', 'sn-05', 'TRAINING IS NEXT.', 'Wrap the day, get warm and open the call.', 'en-GB', 1, true, 1),
  ('session_near', 'sn-06', 'ENTER THE SESSION CLEAN.', 'Gear on. Noise off. Take one look at today''s call.', 'en-GB', 1, true, 1),
  ('session_ready', 'sr-01', 'SESSION READY.', '{session}. Open the call and put the work in.', 'en-GB', 1, true, 1),
  ('session_ready', 'sr-02', 'TODAY''S WORK IS LIVE.', '{session}. Start clean and execute the call.', 'en-GB', 1, true, 1),
  ('session_ready', 'sr-03', 'YOU''RE UP.', 'Open {session} and get to work.', 'en-GB', 1, true, 1),
  ('session_ready', 'sr-04', 'START THE SESSION.', '{session}. Follow the call and earn the day.', 'en-GB', 1, true, 1),
  ('session_ready', 'sr-05', 'PUT THE WORK IN.', '{session}. Start sharp and stay inside the call.', 'en-GB', 1, true, 1),
  ('session_ready', 'sr-06', 'THE NEXT ROUND STARTS NOW.', 'Open {session}. Execute, adapt and finish honest.', 'en-GB', 1, true, 1),
  ('post_session_log', 'pl-01', 'SESSION DONE? LOG IT.', 'Give me effort and pain while the work is still fresh.', 'en-GB', 1, true, 1),
  ('post_session_log', 'pl-02', 'BANK THE SESSION.', 'Log effort and pain now so tomorrow''s call has the full picture.', 'en-GB', 1, true, 1),
  ('post_session_log', 'pl-03', 'CLOSE THE LOOP.', 'Session finished? Add effort, pain and any changes while you remember.', 'en-GB', 1, true, 1),
  ('post_session_log', 'pl-04', 'LOG THE WORK.', 'Tell me what the session cost before the detail fades.', 'en-GB', 1, true, 1),
  ('post_session_log', 'pl-05', 'GIVE ME THE COST.', 'Log effort, pain and changes so the next call sees the full session.', 'en-GB', 1, true, 1),
  ('post_session_log', 'pl-06', 'FINISH THE JOB.', 'The training ends when the effort and pain read is logged.', 'en-GB', 1, true, 1),
  ('post_session_log', 'pl-07', 'CAPTURE THE SESSION.', 'Record what landed, what hurt and what changed.', 'en-GB', 1, true, 1),
  ('post_session_log', 'pl-08', 'TODAY''S DATA MATTERS.', 'Log effort and pain now. Tomorrow''s decision starts here.', 'en-GB', 1, true, 1),
  ('post_session_log', 'pl-low-01', 'TRAINED YET?', 'When you''re done, log effort and pain so I have the full read.', 'en-GB', 1, true, 1),
  ('post_session_log', 'pl-low-02', 'TRAINED YET?', 'If training is finished, log effort, pain and anything that changed.', 'en-GB', 1, true, 1),
  ('injury_recheck', 'ir-01', 'HOW''S {body_area} TODAY?', 'Better, same or worse? Update it before we set the load.', 'en-GB', 1, true, 1),
  ('injury_recheck', 'ir-02', 'UPDATE {body_area}.', 'Give me the current read before training changes the picture.', 'en-GB', 1, true, 1),
  ('injury_recheck', 'ir-03', 'BODY CHECK: {body_area}.', 'Tell me what changed so today''s call stays honest.', 'en-GB', 1, true, 1),
  ('injury_recheck', 'ir-04', 'DON''T GUESS ON {body_area}.', 'Update it now. Better, same or worse decides the next move.', 'en-GB', 1, true, 1),
  ('injury_recheck', 'ir-05', 'RECHECK {body_area}.', 'Give me the current read before another session changes the picture.', 'en-GB', 1, true, 1),
  ('injury_recheck', 'ir-06', 'BETTER, SAME OR WORSE?', 'Update {body_area}. The answer changes what belongs in today''s load.', 'en-GB', 1, true, 1),
  ('injury_recheck', 'ir-07', 'PROTECT THE NEXT SESSION.', 'Give me the current {body_area} read before the work begins.', 'en-GB', 1, true, 1),
  ('injury_recheck', 'ir-08', 'NO BLIND SPOTS TODAY.', '{body_area} needs an update before we make another training call.', 'en-GB', 1, true, 1),
  ('high_pain_followup', 'hp-01', 'HOW DID YOUR BODY SETTLE?', 'Yesterday''s pain was high. Check in before we decide today''s load.', 'en-GB', 1, true, 1),
  ('high_pain_followup', 'hp-02', 'PAIN FOLLOW-UP.', 'Give me the morning read before we set today''s work.', 'en-GB', 1, true, 1),
  ('high_pain_followup', 'hp-03', 'REPORT HOW YOU SETTLED.', 'High pain needs a fresh read before the next session call.', 'en-GB', 1, true, 1),
  ('high_pain_followup', 'hp-04', 'BODY FIRST. THEN THE WORK.', 'Check in now so yesterday''s pain shapes today''s decision.', 'en-GB', 1, true, 1),
  ('high_pain_followup', 'hp-05', 'YESTERDAY LEFT A MARK.', 'Tell me what settled and what did not before today''s load is decided.', 'en-GB', 1, true, 1),
  ('high_pain_followup', 'hp-06', 'FRESH READ. THEN DECIDE.', 'Check in now. High pain yesterday changes how we approach today.', 'en-GB', 1, true, 1),
  ('recovery_checkin', 'rc-01', 'RECOVERY CHECK.', 'How did the body settle after yesterday? Give me the morning read.', 'en-GB', 1, true, 1),
  ('recovery_checkin', 'rc-02', 'HOW DID YOU SETTLE?', 'Sleep, soreness, pain. Recovery days still need an honest read.', 'en-GB', 1, true, 1),
  ('recovery_checkin', 'rc-03', 'REST DAY. REPORT IN.', 'Tell me what recovered and what still needs protecting.', 'en-GB', 1, true, 1),
  ('recovery_checkin', 'rc-04', 'ABSORB THE WORK.', 'Give me the body read before today''s recovery call is set.', 'en-GB', 1, true, 1),
  ('recovery_nudge', 'rn-01', 'RECOVERY IS THE WORK TODAY.', 'Move, eat, hydrate and get the system ready for the next session.', 'en-GB', 1, true, 1),
  ('recovery_nudge', 'rn-02', 'BANK THE RECOVERY DAY.', 'Keep the body moving lightly and make the next hard day easier.', 'en-GB', 1, true, 1),
  ('recovery_nudge', 'rn-03', 'NO HERO WORK TODAY.', 'Recover with intent. Food, fluids, movement and sleep all count.', 'en-GB', 1, true, 1),
  ('recovery_nudge', 'rn-04', 'RESET FOR THE NEXT ROUND.', 'Use today to absorb the work and arrive ready for what is next.', 'en-GB', 1, true, 1),
  ('recovery_nudge', 'rn-05', 'ABSORB THE LOAD.', 'Eat, hydrate, move and let the last session become adaptation.', 'en-GB', 1, true, 1),
  ('recovery_nudge', 'rn-06', 'MAKE TOMORROW EASIER.', 'Keep today light, deliberate and pointed at the next hard day.', 'en-GB', 1, true, 1),
  ('recovery_nudge', 'rn-07', 'DISCIPLINE LOOKS LIKE REST.', 'No extra rounds. Recover, refuel and protect the next session.', 'en-GB', 1, true, 1),
  ('recovery_nudge', 'rn-08', 'LET THE WORK LAND.', 'Move lightly, eat properly and get the system back under you.', 'en-GB', 1, true, 1),
  ('session_modified', 'sm-01', 'ADAPT. DON''T FORCE IT.', 'Today''s session still counts. I''ve changed how we attack it.', 'en-GB', 1, true, 1),
  ('session_modified', 'sm-02', 'THE CALL HAS CHANGED.', 'Train the version in Today. The goal stays; the route changes.', 'en-GB', 1, true, 1),
  ('session_modified', 'sm-03', 'SMART WORK. SAME MISSION.', 'I''ve adjusted today''s load. Follow the change and keep the quality.', 'en-GB', 1, true, 1),
  ('session_modified', 'sm-04', 'PROTECT THE CAMP.', 'Use the modified session. Forcing the old plan costs more than it earns.', 'en-GB', 1, true, 1),
  ('session_modified', 'sm-05', 'ADJUST AND EXECUTE.', 'Today''s work is modified for the body you brought. Open the new call.', 'en-GB', 1, true, 1),
  ('session_modified', 'sm-06', 'WIN THE RIGHT SESSION.', 'The best work today is the adjusted work. Follow it clean.', 'en-GB', 1, true, 1),
  ('session_stop', 'ss-01', 'NO TRAINING TODAY.', 'A safety flag changed the call. Open Today and follow it.', 'en-GB', 1, true, 1),
  ('session_stop', 'ss-02', 'STOP. DO NOT TRAIN.', 'Today''s safety read blocks the session. Open Today and follow the next step.', 'en-GB', 1, true, 1),
  ('session_stop', 'ss-03', 'THE SESSION IS OFF.', 'A safety signal changed the day. Do not force training.', 'en-GB', 1, true, 1),
  ('session_stop', 'ss-04', 'PROTECT THE ATHLETE.', 'No session today. Read the safety call before you do anything else.', 'en-GB', 1, true, 1),
  ('plan_ready', 'pr-01', 'YOUR CAMP IS LXCKED IN.', 'Your final camp is live. Open it and see the full build.', 'en-GB', 1, true, 1),
  ('plan_updated', 'pu-01', 'YOUR PLAN HAS CHANGED.', 'A material camp update is live. Open the plan to see what moved.', 'en-GB', 1, true, 1),
  ('training_week_complete', 'tw-01', 'WEEK COMPLETE.', 'The work is banked. Review it before the next block starts.', 'en-GB', 1, true, 1),
  ('xp_level_up', 'xp-01', 'LEVEL UP.', 'Completed work moved you forward. Open Progress to see the new level.', 'en-GB', 1, true, 1),
  ('fight_countdown', 'fc-01', 'FIGHT WEEK IS CLOSING IN.', '{countdown}. Keep every decision pointed at the fight.', 'en-GB', 1, true, 1),
  ('fight_countdown', 'fc-d14', 'D-14. TWO WEEKS.', 'The final build starts now. Protect quality, recovery and every decision.', 'en-GB', 1, true, 1),
  ('fight_countdown', 'fc-d07', 'D-7. FIGHT WEEK.', 'Freshness, timing, discipline. Nothing outside the mission.', 'en-GB', 1, true, 1),
  ('fight_countdown', 'fc-d03', 'D-3. STAY SHARP.', 'The work is banked. Keep the body calm and the decisions clean.', 'en-GB', 1, true, 1),
  ('fight_countdown', 'fc-d01', 'D-1. READY.', 'No chasing fitness now. Make weight, stay calm and trust the camp.', 'en-GB', 1, true, 1),
  ('coach_message', 'cm-01', '{title}', '{body}', 'en-GB', 1, true, 1)
on conflict (intent, variant_id, locale, template_version) do update
set title_template = excluded.title_template,
    body_template = excluded.body_template,
    active = excluded.active,
    selection_weight = excluded.selection_weight,
    updated_at = timezone('utc', now());

update public.notification_templates
set minimum_timing_confidence = 'high'
where intent = 'session_near' and variant_id = 'sn-01';
