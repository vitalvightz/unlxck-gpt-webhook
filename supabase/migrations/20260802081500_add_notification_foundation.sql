-- Account-level notification preferences and a profile-level delivery ledger.
--
-- Preferences are backend-owned so every device follows the same settings.
-- The delivery ledger is claimed atomically before Web Push fan-out, preventing
-- duplicate decisions across multiple devices, worker retries and restarts.

create table if not exists public.notification_preferences (
  profile_id uuid primary key references public.profiles(id) on delete cascade,
  push_enabled boolean not null default true,
  session_reminders boolean not null default true,
  checkin_reminders boolean not null default true,
  injury_followups boolean not null default true,
  plan_update_alerts boolean not null default true,
  progress_milestones boolean not null default true,
  coach_messages boolean not null default true,
  quiet_hours_enabled boolean not null default true,
  quiet_hours_start time without time zone not null default '22:00',
  quiet_hours_end time without time zone not null default '07:00',
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

drop trigger if exists set_notification_preferences_updated_at on public.notification_preferences;
create trigger set_notification_preferences_updated_at
  before update on public.notification_preferences
  for each row execute function public.set_updated_at();

create table if not exists public.notification_deliveries (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  notification_type text not null
    constraint notification_deliveries_type_length check (char_length(notification_type) between 1 and 64),
  category text not null
    constraint notification_deliveries_category_check check (
      category in (
        'session_reminders',
        'checkin_reminders',
        'injury_followups',
        'plan_update_alerts',
        'progress_milestones',
        'coach_messages'
      )
    ),
  priority smallint not null
    constraint notification_deliveries_priority_check check (priority between 1 and 100),
  title text not null
    constraint notification_deliveries_title_length check (char_length(title) between 1 and 40),
  body text not null
    constraint notification_deliveries_body_length check (char_length(body) between 1 and 90),
  url text not null
    constraint notification_deliveries_url_check check (char_length(url) between 1 and 500 and left(url, 1) = '/'),
  tag text not null
    constraint notification_deliveries_tag_length check (char_length(tag) between 1 and 80),
  dedupe_key text not null
    constraint notification_deliveries_dedupe_length check (char_length(dedupe_key) between 1 and 160),
  expires_at timestamptz not null,
  status text not null default 'pending'
    constraint notification_deliveries_status_check check (status in ('pending', 'sent', 'partial', 'failed')),
  claim_token uuid not null default gen_random_uuid(),
  claimed_at timestamptz not null default timezone('utc', now()),
  attempt_count integer not null default 1
    constraint notification_deliveries_attempt_count_check check (attempt_count between 1 and 3),
  delivered_count integer not null default 0
    constraint notification_deliveries_delivered_count_check check (delivered_count >= 0),
  error_code text
    constraint notification_deliveries_error_code_length check (error_code is null or char_length(error_code) <= 120),
  sent_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint notification_deliveries_profile_dedupe_key unique (profile_id, dedupe_key)
);

create index if not exists notification_deliveries_profile_created_idx
  on public.notification_deliveries (profile_id, created_at desc);
create index if not exists notification_deliveries_pending_idx
  on public.notification_deliveries (status, claimed_at)
  where status in ('pending', 'failed');

drop trigger if exists set_notification_deliveries_updated_at on public.notification_deliveries;
create trigger set_notification_deliveries_updated_at
  before update on public.notification_deliveries
  for each row execute function public.set_updated_at();

alter table public.notification_preferences enable row level security;
alter table public.notification_deliveries enable row level security;

-- Athletes may read their own settings/history, but all writes remain routed
-- through the authenticated backend service role.
drop policy if exists "notification_preferences_owner_select" on public.notification_preferences;
create policy "notification_preferences_owner_select" on public.notification_preferences
for select using (profile_id = auth.uid());

drop policy if exists "notification_deliveries_owner_select" on public.notification_deliveries;
create policy "notification_deliveries_owner_select" on public.notification_deliveries
for select using (profile_id = auth.uid());

revoke all on public.notification_preferences from anon;
revoke insert, update, delete on public.notification_preferences from authenticated;
grant select on public.notification_preferences to authenticated;
grant all on public.notification_preferences to service_role;

revoke all on public.notification_deliveries from anon;
revoke insert, update, delete on public.notification_deliveries from authenticated;
grant select on public.notification_deliveries to authenticated;
grant all on public.notification_deliveries to service_role;

create or replace function public.claim_notification_delivery(
  p_profile_id uuid,
  p_notification_type text,
  p_category text,
  p_priority integer,
  p_title text,
  p_body text,
  p_url text,
  p_tag text,
  p_dedupe_key text,
  p_expires_at timestamptz
)
returns setof public.notification_deliveries
language plpgsql
security definer
set search_path = public
as $$
declare
  v_claim_token uuid := gen_random_uuid();
begin
  if p_expires_at <= timezone('utc', now()) then
    return;
  end if;

  return query
  insert into public.notification_deliveries (
    profile_id,
    notification_type,
    category,
    priority,
    title,
    body,
    url,
    tag,
    dedupe_key,
    expires_at,
    status,
    claim_token,
    claimed_at,
    attempt_count
  ) values (
    p_profile_id,
    p_notification_type,
    p_category,
    p_priority,
    p_title,
    p_body,
    p_url,
    p_tag,
    p_dedupe_key,
    p_expires_at,
    'pending',
    v_claim_token,
    timezone('utc', now()),
    1
  )
  on conflict (profile_id, dedupe_key) do nothing
  returning *;

  if found then
    return;
  end if;

  -- A crashed worker may leave a claim pending. Reclaim only after 15 minutes.
  -- Failed deliveries are retryable up to the hard three-attempt ceiling.
  return query
  update public.notification_deliveries
  set
    notification_type = p_notification_type,
    category = p_category,
    priority = p_priority,
    title = p_title,
    body = p_body,
    url = p_url,
    tag = p_tag,
    expires_at = p_expires_at,
    status = 'pending',
    claim_token = v_claim_token,
    claimed_at = timezone('utc', now()),
    attempt_count = attempt_count + 1,
    delivered_count = 0,
    error_code = null,
    sent_at = null
  where profile_id = p_profile_id
    and dedupe_key = p_dedupe_key
    and p_expires_at > timezone('utc', now())
    and attempt_count < 3
    and (
      status = 'failed'
      or (
        status = 'pending'
        and claimed_at <= timezone('utc', now()) - interval '15 minutes'
      )
    )
  returning *;
end;
$$;

create or replace function public.finalize_notification_delivery(
  p_delivery_id uuid,
  p_claim_token uuid,
  p_status text,
  p_delivered_count integer,
  p_error_code text default null
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_updated integer;
begin
  if p_status not in ('sent', 'partial', 'failed') then
    raise exception 'invalid_notification_delivery_status';
  end if;

  update public.notification_deliveries
  set
    status = p_status,
    delivered_count = greatest(0, p_delivered_count),
    error_code = nullif(left(coalesce(p_error_code, ''), 120), ''),
    sent_at = case
      when p_status in ('sent', 'partial') then timezone('utc', now())
      else null
    end
  where id = p_delivery_id
    and claim_token = p_claim_token
    and status = 'pending';

  get diagnostics v_updated = row_count;
  return v_updated = 1;
end;
$$;

revoke all on function public.claim_notification_delivery(
  uuid, text, text, integer, text, text, text, text, text, timestamptz
) from public, anon, authenticated;
grant execute on function public.claim_notification_delivery(
  uuid, text, text, integer, text, text, text, text, text, timestamptz
) to service_role;

revoke all on function public.finalize_notification_delivery(
  uuid, uuid, text, integer, text
) from public, anon, authenticated;
grant execute on function public.finalize_notification_delivery(
  uuid, uuid, text, integer, text
) to service_role;
