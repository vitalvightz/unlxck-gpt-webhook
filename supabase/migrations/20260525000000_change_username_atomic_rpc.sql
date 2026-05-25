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
  v_next_available timestamptz;
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

  select coalesce(jsonb_agg(to_jsonb(parsed_at)), '[]'::jsonb),
         min(parsed_at)
  into v_recent
       ,v_next_available
  from (
    select candidate.parsed_at
    from (
      select case
        when value_text ~* '^\d{4}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}(\.\d+)?(z|[+-]\d{2}:\d{2})$'
          then value_text::timestamptz
        else null
      end as parsed_at
      from jsonb_array_elements_text(
        case
          when jsonb_typeof(v_profile.username_change_history) = 'array'
            then v_profile.username_change_history
          else '[]'::jsonb
        end
      ) as value_text
    ) candidate
    where candidate.parsed_at is not null and candidate.parsed_at >= v_cutoff
  ) filtered;

  if jsonb_array_length(v_recent) >= 4 then
    raise exception 'username_rate_limit_exceeded:%',
      coalesce((v_next_available + interval '30 days')::text, '');
  end if;

  update public.profiles
  set
    username = p_username,
    username_change_history = v_recent || to_jsonb(v_now),
    updated_at = v_now
  where id = p_profile_id;
end;
$$;

revoke execute on function public.change_profile_username(uuid, text) from public;
revoke execute on function public.change_profile_username(uuid, text) from anon;
revoke execute on function public.change_profile_username(uuid, text) from authenticated;
grant execute on function public.change_profile_username(uuid, text) to service_role;
