-- PostgREST resolves JSON whole numbers as PostgreSQL integer arguments. The
-- first production migration declared p_priority as smallint, which made the
-- RPC unavailable to normal supabase-py calls even though the stored column is
-- correctly bounded to smallint. Replace only the function signature; the table
-- and its 1-100 constraint remain unchanged.

drop function if exists public.claim_notification_delivery(
  uuid, text, text, smallint, text, text, text, text, text, timestamptz
);

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

revoke all on function public.claim_notification_delivery(
  uuid, text, text, integer, text, text, text, text, text, timestamptz
) from public, anon, authenticated;
grant execute on function public.claim_notification_delivery(
  uuid, text, text, integer, text, text, text, text, text, timestamptz
) to service_role;
