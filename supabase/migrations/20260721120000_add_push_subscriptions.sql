-- Web push subscriptions: one row per (profile, browser push endpoint).
--
-- Backs athlete notifications: "your final plan is ready" when the enhanced
-- card lands, and the daily morning check-in nudge. The subscription payload
-- (endpoint + p256dh/auth keys) comes from PushManager.subscribe() in the PWA
-- and is only ever used server-side with the VAPID private key.
--
-- timezone is the device's IANA timezone captured at subscribe time; the
-- morning scheduler uses it to send at local morning. morning_last_sent_day is
-- the athlete-local date of the last morning nudge, the per-day dedupe key.
--
-- Write path: service role only (backend). Read path: owners read their own
-- rows, admins read everything — matching today_checkins/session_completions.

create table if not exists public.push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  endpoint text not null,
  p256dh text not null,
  auth text not null,
  timezone text not null default '',
  morning_last_sent_day date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- A push endpoint identifies one browser install; re-subscribing replaces
  -- the row rather than accumulating stale duplicates.
  constraint push_subscriptions_endpoint_key unique (endpoint)
);

create index if not exists push_subscriptions_profile_idx
  on public.push_subscriptions (profile_id);

drop trigger if exists set_push_subscriptions_updated_at on public.push_subscriptions;
create trigger set_push_subscriptions_updated_at
  before update on public.push_subscriptions
  for each row execute function public.set_updated_at();

alter table public.push_subscriptions enable row level security;

drop policy if exists "push_subscriptions_owner_select" on public.push_subscriptions;
create policy "push_subscriptions_owner_select" on public.push_subscriptions
for select using (profile_id = auth.uid() or public.is_admin());

revoke all on public.push_subscriptions from anon;
revoke insert, update, delete on public.push_subscriptions from authenticated;
grant select on public.push_subscriptions to authenticated;
grant all on public.push_subscriptions to service_role;
