-- Cap feedback XP independently of the award-RPC compatibility layer.
-- This migration is safe for the currently deployed backend because feedback
-- dates are derived from the persisted feedback row inside this RPC.

create or replace function public.reconcile_feedback_xp(
  p_athlete_id uuid,
  p_feedback_id uuid,
  p_target_amount integer
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_key text := 'feedback:' || p_feedback_id::text;
  v_existing public.xp_awards%rowtype;
  v_previous_total bigint;
  v_total bigint;
  v_delta integer := 0;
  v_award public.xp_awards%rowtype;
  v_recent_awards jsonb;
  v_feedback_created_at timestamptz;
  v_calendar_date date;
  v_daily_count integer := 0;
  v_cap_reached boolean := false;
begin
  if coalesce(auth.role(), '') <> 'service_role' then
    raise exception 'reconcile_feedback_xp is restricted to the backend service role'
      using errcode = '42501';
  end if;

  if p_athlete_id is null or not exists (
    select 1
    from public.profiles
    where id = p_athlete_id
      and role::text = 'athlete'
  ) then
    raise exception 'xp athlete profile not found' using errcode = '23503';
  end if;

  select created_at
  into v_feedback_created_at
  from public.beta_feedback
  where id = p_feedback_id
    and submitted_by_profile_id = p_athlete_id;

  if v_feedback_created_at is null then
    raise exception 'feedback not found for athlete' using errcode = '23503';
  end if;

  if p_target_amount not in (1, 3) then
    raise exception 'invalid feedback XP target' using errcode = '22023';
  end if;

  -- UTC makes the cap deterministic and immune to client timezone changes.
  v_calendar_date := (v_feedback_created_at at time zone 'UTC')::date;

  perform pg_advisory_xact_lock(hashtextextended(p_athlete_id::text, 0));

  insert into public.xp_accounts (athlete_id)
  values (p_athlete_id)
  on conflict (athlete_id) do nothing;

  select total_xp
  into v_previous_total
  from public.xp_accounts
  where athlete_id = p_athlete_id
  for update;

  select *
  into v_existing
  from public.xp_awards
  where athlete_id = p_athlete_id
    and idempotency_key = v_key
  for update;

  if v_existing.id is null then
    select count(*)
    into v_daily_count
    from public.xp_awards
    where athlete_id = p_athlete_id
      and action in ('feedback_submitted', 'feedback_with_comment')
      and calendar_date = v_calendar_date;

    if v_daily_count >= 3 then
      v_cap_reached := true;
    else
      insert into public.xp_awards (
        athlete_id,
        action,
        amount,
        idempotency_key,
        calendar_date
      ) values (
        p_athlete_id,
        case
          when p_target_amount = 3 then 'feedback_with_comment'
          else 'feedback_submitted'
        end,
        p_target_amount,
        v_key,
        v_calendar_date
      )
      returning * into v_award;
      v_delta := p_target_amount;
    end if;
  elsif v_existing.amount < p_target_amount then
    -- A useful comment may upgrade an existing 1 XP record even after the daily
    -- new-record cap is reached. It cannot create a fourth feedback award.
    update public.xp_awards
    set
      action = 'feedback_with_comment',
      amount = 3
    where id = v_existing.id
    returning * into v_award;
    v_delta := 3 - v_existing.amount;
  else
    v_award := v_existing;
  end if;

  if v_delta > 0 then
    update public.xp_accounts
    set
      total_xp = total_xp + v_delta,
      updated_at = clock_timestamp()
    where athlete_id = p_athlete_id
    returning total_xp into v_total;
  else
    v_total := v_previous_total;
  end if;

  select coalesce(
    jsonb_agg(item order by awarded_at desc, id desc),
    '[]'::jsonb
  )
  into v_recent_awards
  from (
    select
      award.id,
      award.awarded_at,
      jsonb_strip_nulls(jsonb_build_object(
        'id', award.id,
        'action', award.action,
        'amount', award.amount,
        'awarded_at', award.awarded_at,
        'calendar_date', award.calendar_date
      )) item
    from public.xp_awards award
    where award.athlete_id = p_athlete_id
    order by award.awarded_at desc, award.id desc
    limit 20
  ) recent;

  return jsonb_build_object(
    'state', jsonb_build_object(
      'total_xp', v_total,
      'recent_awards', v_recent_awards
    ),
    'previous_total_xp', v_previous_total,
    'awarded', v_delta > 0,
    'xp_delta', v_delta,
    'cap_reached', v_cap_reached,
    'award', case
      when v_award.id is not null then jsonb_strip_nulls(jsonb_build_object(
        'id', v_award.id,
        'action', v_award.action,
        'amount', v_award.amount,
        'awarded_at', v_award.awarded_at,
        'calendar_date', v_award.calendar_date
      ))
      else 'null'::jsonb
    end
  );
end;
$$;

revoke all on function public.reconcile_feedback_xp(uuid, uuid, integer)
  from public, anon, authenticated;
grant execute on function public.reconcile_feedback_xp(uuid, uuid, integer)
  to service_role;
