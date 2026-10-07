-- Today reads must not write.
--
-- Every Today build syncs the active plan's intake injuries through
-- adopt_or_create_intake_injury_flag_with_wound_fields. Its wound-field fill
-- ran an UPDATE on every call, even when the row already had every field, and
-- the set_injury_flags_updated_at trigger stamps updated_at on any UPDATE. So
-- each read of Today moved the injury's updated_at.
--
-- The live session prescription's revision includes each open injury's
-- updated_at (it must change when the injury really changes). Starting a
-- session rebuilds Today, which bumped updated_at again, so the revision the
-- athlete was shown never matched and every start was refused with "Your
-- session prescription changed".
--
-- The fill now only updates the row when it actually supplies a missing value,
-- the same rule the in-memory store (tests/support.py) already follows.

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
  where id = v_flag_id
    -- Only when a missing wound field is actually filled in.
    and (
      (skin_integrity is null and p_skin_integrity is not null)
      or (bleeding_status is null and p_bleeding_status is not null)
      or (coverable is null and p_coverable is not null)
      or (drainage is null and p_drainage is not null)
      or (
        coalesce(infection_signs, '[]'::jsonb) = '[]'::jsonb
        and jsonb_typeof(coalesce(p_infection_signs, '[]'::jsonb)) = 'array'
        and coalesce(p_infection_signs, '[]'::jsonb) <> '[]'::jsonb
      )
    );

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
