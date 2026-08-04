-- Preserve structured wound-safety answers when an intake injury is atomically
-- adopted or created. The base RPC still owns identity, duplicate cleanup and
-- status preservation; this wrapper fills only fields that are currently empty,
-- so later daily injury updates always remain authoritative.
create or replace function public.adopt_or_create_intake_injury_flag_with_wound_fields(
  p_athlete_id uuid,
  p_plan_id uuid,
  p_source_key text,
  p_body_area text,
  p_description text,
  p_severity text default 'moderate',
  p_status text default 'open',
  p_resolved_at timestamptz default null,
  p_skin_integrity text default null,
  p_bleeding_status text default null,
  p_infection_signs jsonb default '[]'::jsonb,
  p_coverable text default null,
  p_drainage text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_flag jsonb;
  v_flag_id uuid;
begin
  v_flag := public.adopt_or_create_intake_injury_flag(
    p_athlete_id,
    p_plan_id,
    p_source_key,
    p_body_area,
    p_description,
    p_severity,
    p_status,
    p_resolved_at
  );

  v_flag_id := nullif(v_flag ->> 'id', '')::uuid;
  if v_flag_id is null then
    return v_flag;
  end if;

  update public.injury_flags
  set
    skin_integrity = coalesce(skin_integrity, p_skin_integrity),
    bleeding_status = coalesce(bleeding_status, p_bleeding_status),
    infection_signs = case
      when coalesce(infection_signs, '[]'::jsonb) = '[]'::jsonb
        and jsonb_typeof(coalesce(p_infection_signs, '[]'::jsonb)) = 'array'
        and coalesce(p_infection_signs, '[]'::jsonb) <> '[]'::jsonb
      then p_infection_signs
      else infection_signs
    end,
    coverable = coalesce(coverable, p_coverable),
    drainage = coalesce(drainage, p_drainage)
  where id = v_flag_id;

  select to_jsonb(flag)
  into v_flag
  from public.injury_flags flag
  where flag.id = v_flag_id;

  return v_flag;
end;
$$;

revoke all on function public.adopt_or_create_intake_injury_flag_with_wound_fields(
  uuid,
  uuid,
  text,
  text,
  text,
  text,
  text,
  timestamptz,
  text,
  text,
  jsonb,
  text,
  text
) from public, anon, authenticated;

grant execute on function public.adopt_or_create_intake_injury_flag_with_wound_fields(
  uuid,
  uuid,
  text,
  text,
  text,
  text,
  text,
  timestamptz,
  text,
  text,
  jsonb,
  text,
  text
) to service_role;
