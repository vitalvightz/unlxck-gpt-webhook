create or replace function public.change_profile_username(
  p_profile_id uuid,
  p_username text
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_profile public.profiles%rowtype;
  v_now timestamptz := now();
  v_cutoff timestamptz := v_now - interval '30 days';
  v_recent jsonb := '[]'::jsonb;
begin
  select *
  into v_profile
  from public.profiles
  where id = p_profile_id
  for update;

  if not found then
    raise exception 'profile_not_found';
  end if;

  if v_profile.username is not null and v_profile.username = p_username then
    return;
  end if;

  select coalesce(jsonb_agg(value), '[]'::jsonb)
  into v_recent
  from jsonb_array_elements(v_profile.username_change_history) as value
  where (value #>> '{}')::timestamptz >= v_cutoff;

  if jsonb_array_length(v_recent) >= 4 then
    raise exception 'username_rate_limit_exceeded';
  end if;

  update public.profiles
  set
    username = p_username,
    username_change_history = v_recent || to_jsonb(v_now),
    updated_at = v_now
  where id = p_profile_id;
end;
$$;
