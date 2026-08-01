-- Durable, account-scoped XP.
--
-- The browser may read only the signed-in profile's rows. Award mutations are
-- deliberately unavailable to anon/authenticated roles and flow through the
-- FastAPI service-role boundary plus the atomic RPC below. This keeps action
-- values server-owned and makes retries safe through a per-account idempotency
-- key and a second daily-login uniqueness constraint.

create table if not exists public.xp_accounts (
  athlete_id uuid primary key references public.profiles(id) on delete cascade,
  total_xp bigint not null default 0 check (total_xp >= 0),
  last_daily_login_date date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.xp_awards (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  action text not null check (action in (
    'daily_login',
    'training_logged',
    'planned_session_completed',
    'recommended_fighter_content_watched',
    'full_training_week_completed'
  )),
  amount integer not null check (
    (action = 'daily_login' and amount = 10)
    or (action = 'training_logged' and amount = 25)
    or (action = 'planned_session_completed' and amount = 50)
    or (action = 'recommended_fighter_content_watched' and amount = 10)
    or (action = 'full_training_week_completed' and amount = 100)
  ),
  idempotency_key text not null check (
    char_length(btrim(idempotency_key)) between 1 and 200
  ),
  calendar_date date,
  awarded_at timestamptz not null default now(),
  constraint xp_awards_daily_calendar_required check (
    (action = 'daily_login' and calendar_date is not null)
    or (action <> 'daily_login' and calendar_date is null)
  ),
  constraint xp_awards_athlete_idempotency_key
    unique (athlete_id, idempotency_key)
);

create unique index if not exists xp_awards_one_daily_login_per_calendar_date
  on public.xp_awards (athlete_id, calendar_date)
  where action = 'daily_login';

create index if not exists xp_awards_athlete_recent_idx
  on public.xp_awards (athlete_id, awarded_at desc, id desc);

alter table public.xp_accounts enable row level security;
alter table public.xp_accounts force row level security;
alter table public.xp_awards enable row level security;
alter table public.xp_awards force row level security;

drop policy if exists "xp_accounts_owner_select" on public.xp_accounts;
create policy "xp_accounts_owner_select" on public.xp_accounts
for select to authenticated
using ((select auth.uid()) = athlete_id);

drop policy if exists "xp_awards_owner_select" on public.xp_awards;
create policy "xp_awards_owner_select" on public.xp_awards
for select to authenticated
using ((select auth.uid()) = athlete_id);

revoke all on table public.xp_accounts from public, anon, authenticated;
revoke all on table public.xp_awards from public, anon, authenticated;
grant select on table public.xp_accounts to authenticated;
grant select on table public.xp_awards to authenticated;
grant select, insert, update, delete on table public.xp_accounts to service_role;
grant select, insert, update, delete on table public.xp_awards to service_role;

create or replace function public.award_athlete_xp(
  p_athlete_id uuid,
  p_action text,
  p_idempotency_key text,
  p_calendar_date date default null
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_action text := btrim(coalesce(p_action, ''));
  v_key text := btrim(coalesce(p_idempotency_key, ''));
  v_amount integer;
  v_previous_total bigint;
  v_total bigint;
  v_last_daily_login_date date;
  v_award public.xp_awards%rowtype;
  v_awarded boolean := false;
  v_recent_awards jsonb;
begin
  if coalesce(auth.role(), '') <> 'service_role' then
    raise exception 'award_athlete_xp is restricted to the backend service role'
      using errcode = '42501';
  end if;

  if p_athlete_id is null or not exists (
    select 1 from public.profiles where id = p_athlete_id
  ) then
    raise exception 'xp athlete profile not found' using errcode = '23503';
  end if;

  if char_length(v_key) not between 1 and 200 then
    raise exception 'invalid XP idempotency key' using errcode = '22023';
  end if;

  v_amount := case v_action
    when 'daily_login' then 10
    when 'training_logged' then 25
    when 'planned_session_completed' then 50
    when 'recommended_fighter_content_watched' then 10
    when 'full_training_week_completed' then 100
    else null
  end;

  if v_amount is null then
    raise exception 'unknown XP action' using errcode = '22023';
  end if;

  if v_action = 'daily_login' and p_calendar_date is null then
    raise exception 'daily login XP requires a calendar date' using errcode = '22023';
  end if;

  -- Serialize all awards for one account so the aggregate can never lose an
  -- increment under concurrent requests. The ledger insert remains the source
  -- of idempotency; the account row is updated only when that insert succeeds.
  perform pg_advisory_xact_lock(hashtextextended(p_athlete_id::text, 0));

  insert into public.xp_accounts (athlete_id)
  values (p_athlete_id)
  on conflict (athlete_id) do nothing;

  select total_xp, last_daily_login_date
    into v_previous_total, v_last_daily_login_date
  from public.xp_accounts
  where athlete_id = p_athlete_id
  for update;

  if v_action <> 'daily_login'
    or v_last_daily_login_date is null
    or p_calendar_date > v_last_daily_login_date then
    insert into public.xp_awards (
      athlete_id,
      action,
      amount,
      idempotency_key,
      calendar_date
    )
    values (
      p_athlete_id,
      v_action,
      v_amount,
      v_key,
      case when v_action = 'daily_login' then p_calendar_date else null end
    )
    on conflict do nothing
    returning * into v_award;

    v_awarded := v_award.id is not null;
  end if;

  if v_awarded then
    update public.xp_accounts
    set
      total_xp = total_xp + v_amount,
      last_daily_login_date = case
        when v_action = 'daily_login' then p_calendar_date
        else last_daily_login_date
      end,
      updated_at = clock_timestamp()
    where athlete_id = p_athlete_id
    returning total_xp, last_daily_login_date
      into v_total, v_last_daily_login_date;
  else
    v_total := v_previous_total;
  end if;

  select coalesce(
    jsonb_agg(recent.item order by recent.awarded_at desc, recent.id desc),
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
      )) as item
    from public.xp_awards as award
    where award.athlete_id = p_athlete_id
    order by award.awarded_at desc, award.id desc
    limit 20
  ) as recent;

  return jsonb_build_object(
    'state', jsonb_build_object(
      'total_xp', v_total,
      'last_daily_login_date', v_last_daily_login_date,
      'recent_awards', v_recent_awards
    ),
    'previous_total_xp', v_previous_total,
    'awarded', v_awarded,
    'award', case
      when v_awarded then jsonb_strip_nulls(jsonb_build_object(
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

revoke all on function public.award_athlete_xp(uuid, text, text, date)
  from public, anon, authenticated;
grant execute on function public.award_athlete_xp(uuid, text, text, date)
  to service_role;
