-- One injury, one row, across plans.
--
-- An intake injury's source_key includes its plan id, so generating a new plan
-- from a camp setup that still lists the same injury inserted a second open
-- row, and Today showed the injury twice.
--
-- Identity now holds across plans: when a plan's intake lists an injury and
-- the athlete already has an open or monitoring intake injury from another
-- plan with the same body area AND the same description (the identity the
-- source_key already hashes), that row is carried onto the new plan (its
-- history, rehab stage and check-ins stay attached) instead of a new row being
-- inserted. Body area alone is never enough: an ankle sprain and an ankle
-- blister are different injuries and are never merged. A resolved injury is
-- never carried: listing it again opens a new episode, as before.
--
-- The carry-over writes only when a plan's key is first seen, so repeated
-- Today reads still never write (see 20261007193500).

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
  v_carry_id uuid;
  v_area text := replace(
    replace(replace(lower(btrim(coalesce(p_body_area, ''))), '-', '_'), '/', '_'),
    ' ',
    '_'
  );
  v_description text := regexp_replace(
    lower(btrim(coalesce(p_description, ''))), '\s+', ' ', 'g'
  );
begin
  -- Serialize carry-overs per athlete, ahead of the base RPC's per-key lock.
  perform pg_advisory_xact_lock(
    hashtextextended(p_athlete_id::text || ':intake-carry', 0)
  );

  if p_plan_id is not null
    and nullif(btrim(p_source_key), '') is not null
    and v_area <> ''
    and not exists (
      select 1 from public.injury_flags
      where athlete_id = p_athlete_id and source_key = p_source_key
    )
  then
    select id
    into v_carry_id
    from public.injury_flags
    where athlete_id = p_athlete_id
      and source = 'intake'
      and plan_id is distinct from p_plan_id
      and lower(btrim(coalesce(status, ''))) in ('open', 'monitoring')
      and replace(
        replace(replace(lower(btrim(coalesce(body_area, ''))), '-', '_'), '/', '_'),
        ' ',
        '_'
      ) = v_area
      and regexp_replace(lower(btrim(coalesce(description, ''))), '\s+', ' ', 'g') = v_description
    order by
      created_at asc,
      id asc
    limit 1
    for update;

    if v_carry_id is not null then
      update public.injury_flags
      set plan_id = p_plan_id, source_key = p_source_key
      where id = v_carry_id;
    end if;
  end if;

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
  uuid, uuid, text, text, text, text, text, timestamptz, text, text, jsonb, text, text
) from public, anon, authenticated;

grant execute on function public.adopt_or_create_intake_injury_flag_with_wound_fields(
  uuid, uuid, text, text, text, text, text, timestamptz, text, text, jsonb, text, text
) to service_role;

-- Merge the duplicates already created: for each athlete and injury identity
-- (body area + description) whose open or monitoring intake rows come from
-- more than one plan (one row per plan), keep the oldest row, move it onto the
-- newest row's plan and key, and retire the rest with a distinct audit key.
-- Rows that differ in description are different injuries and are untouched.
create temporary table intake_injury_merge as
with live as (
  select
    id,
    athlete_id,
    plan_id,
    source_key,
    created_at,
    replace(
      replace(replace(lower(btrim(coalesce(body_area, ''))), '-', '_'), '/', '_'),
      ' ',
      '_'
    ) as area,
    regexp_replace(lower(btrim(coalesce(description, ''))), '\s+', ' ', 'g') as identity_description
  from public.injury_flags
  where source = 'intake'
    and plan_id is not null
    and lower(btrim(coalesce(status, ''))) in ('open', 'monitoring')
),
groups as (
  select athlete_id, area, identity_description
  from live
  where area <> ''
  group by athlete_id, area, identity_description
  having count(*) > 1 and count(*) = count(distinct plan_id)
)
select
  live.*,
  first_value(live.id) over oldest as keep_id,
  first_value(live.plan_id) over newest as new_plan_id,
  first_value(live.source_key) over newest as new_source_key
from live
join groups using (athlete_id, area, identity_description)
window
  oldest as (partition by live.athlete_id, live.area, live.identity_description
    order by live.created_at asc, live.id asc
    rows between unbounded preceding and unbounded following),
  newest as (partition by live.athlete_id, live.area, live.identity_description
    order by live.created_at desc, live.id desc
    rows between unbounded preceding and unbounded following);

update public.injury_flags flags
set
  source_key = coalesce(merge.source_key, 'intake:' || merge.plan_id::text) || ':merged-duplicate:' || flags.id::text,
  status = 'resolved',
  resolved_at = coalesce(flags.resolved_at, now())
from intake_injury_merge merge
where flags.id = merge.id
  and merge.id <> merge.keep_id;

update public.injury_flags flags
set
  plan_id = merge.new_plan_id,
  source_key = merge.new_source_key
from intake_injury_merge merge
where flags.id = merge.id
  and merge.id = merge.keep_id
  and flags.plan_id is distinct from merge.new_plan_id;

drop table intake_injury_merge;
