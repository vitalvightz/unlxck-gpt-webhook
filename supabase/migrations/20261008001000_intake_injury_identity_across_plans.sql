-- One injury, one row, across plans.
--
-- An intake injury's source_key hashes its plan id, body area and description,
-- and the description carries the athlete's "[training_impact:...]" choice.
-- Every regenerated plan, and every change of that choice in camp setup,
-- therefore inserted a new open row for the same injury, and Today showed it
-- twice.
--
-- An intake injury now has a plan-independent identity, ``intake_identity``,
-- computed by the API from the structured camp-setup fields (body zone + injury
-- type; see api/services/intake_injury_sync.py). When a plan's intake lists an
-- injury whose identity matches an open or monitoring intake injury from
-- another plan, that row is carried onto the plan (its history, rehab stage and
-- check-ins stay attached) and takes the camp setup's current description and
-- severity, instead of a new row being inserted. Rows from before this change
-- have no identity yet; they match on body area plus description with the
-- training-impact tag removed. Different injuries (an ankle sprain and an ankle
-- blister) never match. A resolved injury is never carried.
--
-- The carry writes only the first time a plan's key is seen, so repeated Today
-- reads still never write (see 20261007193500).

alter table public.injury_flags add column if not exists intake_identity text;

create index if not exists injury_flags_athlete_intake_identity_idx
  on public.injury_flags (athlete_id, intake_identity)
  where intake_identity is not null;

create or replace function public.intake_injury_area_key(p_value text)
returns text
language sql
immutable
set search_path = public
as $$
  select replace(
    replace(replace(lower(btrim(coalesce(p_value, ''))), '-', '_'), '/', '_'),
    ' ',
    '_'
  );
$$;

-- The description without the athlete's training-impact choice, which is a
-- setting on the injury, not part of what the injury is.
create or replace function public.intake_injury_description_key(p_value text)
returns text
language sql
immutable
set search_path = public
as $$
  select btrim(regexp_replace(
    regexp_replace(lower(coalesce(p_value, '')), '\s?\[training_impact:[^\]]*\]', '', 'g'),
    '\s+',
    ' ',
    'g'
  ));
$$;

revoke all on function public.intake_injury_area_key(text) from public, anon, authenticated;
revoke all on function public.intake_injury_description_key(text) from public, anon, authenticated;
grant execute on function public.intake_injury_area_key(text) to service_role;
grant execute on function public.intake_injury_description_key(text) to service_role;

-- The new parameter has a default, so the old 13-argument signature would make
-- every call ambiguous. Replace it.
drop function if exists public.adopt_or_create_intake_injury_flag_with_wound_fields(
  uuid, uuid, text, text, text, text, text, timestamptz, text, text, jsonb, text, text
);

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
  p_drainage text default null,
  p_intake_identity text default null
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
  v_identity text := nullif(btrim(coalesce(p_intake_identity, '')), '');
  v_severity text := nullif(lower(btrim(coalesce(p_severity, ''))), '');
begin
  -- Serialize carry-overs per athlete, ahead of the base RPC's per-key lock.
  perform pg_advisory_xact_lock(
    hashtextextended(p_athlete_id::text || ':intake-carry', 0)
  );

  if p_plan_id is not null
    and nullif(btrim(p_source_key), '') is not null
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
      and lower(btrim(coalesce(status, ''))) in ('open', 'monitoring')
      -- Only from other plans: this plan's own rows (another injury it lists,
      -- or unkeyed legacy rows the base RPC adopts) are not carried.
      and plan_id is distinct from p_plan_id
      and (
        (v_identity is not null and intake_identity = v_identity)
        or (
          intake_identity is null
          and public.intake_injury_area_key(body_area) <> ''
          and public.intake_injury_area_key(body_area) = public.intake_injury_area_key(p_body_area)
          and public.intake_injury_description_key(description)
            = public.intake_injury_description_key(p_description)
        )
      )
    order by (intake_identity is not null) desc, created_at asc, id asc
    limit 1
    for update;

    if v_carry_id is not null then
      update public.injury_flags
      set
        plan_id = p_plan_id,
        source_key = p_source_key,
        intake_identity = coalesce(v_identity, intake_identity),
        description = coalesce(p_description, description),
        -- Camp setup's severity is the athlete's own; a surface-system floor
        -- keeps owning the severity it raised.
        severity = case
          when severity_source is distinct from 'surface_system'
            and v_severity in ('mild', 'moderate', 'severe')
          then v_severity
          else severity
        end
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
    drainage = coalesce(drainage, p_drainage),
    intake_identity = coalesce(intake_identity, v_identity)
  where id = v_flag_id
    -- Only when a missing field is actually filled in.
    and (
      (skin_integrity is null and p_skin_integrity is not null)
      or (bleeding_status is null and p_bleeding_status is not null)
      or (coverable is null and p_coverable is not null)
      or (drainage is null and p_drainage is not null)
      or (intake_identity is null and v_identity is not null)
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
  uuid, uuid, text, text, text, text, text, timestamptz, text, text, jsonb, text, text, text
) from public, anon, authenticated;

grant execute on function public.adopt_or_create_intake_injury_flag_with_wound_fields(
  uuid, uuid, text, text, text, text, text, timestamptz, text, text, jsonb, text, text, text
) to service_role;

-- Merge the duplicates already created: open or monitoring intake rows of one
-- athlete with the same body area and the same description (training-impact
-- tag removed), from more than one plan and one row per plan. The oldest row
-- keeps its history and moves onto the newest row's plan, key, description and
-- severity; the others are resolved under a distinct audit key. Rows that
-- differ in description are different injuries and are untouched.
create temporary table intake_injury_merge as
with live as (
  select
    id,
    athlete_id,
    plan_id,
    source_key,
    description,
    severity,
    created_at,
    public.intake_injury_area_key(body_area) as area,
    public.intake_injury_description_key(description) as description_key
  from public.injury_flags
  where source = 'intake'
    and plan_id is not null
    and lower(btrim(coalesce(status, ''))) in ('open', 'monitoring')
),
groups as (
  select athlete_id, area, description_key
  from live
  where area <> ''
  group by athlete_id, area, description_key
  having count(*) > 1 and count(*) = count(distinct plan_id)
)
select
  live.*,
  first_value(live.id) over oldest as keep_id,
  first_value(live.plan_id) over newest as new_plan_id,
  first_value(live.source_key) over newest as new_source_key,
  first_value(live.description) over newest as new_description,
  first_value(live.severity) over newest as new_severity
from live
join groups using (athlete_id, area, description_key)
window
  oldest as (partition by live.athlete_id, live.area, live.description_key
    order by live.created_at asc, live.id asc
    rows between unbounded preceding and unbounded following),
  newest as (partition by live.athlete_id, live.area, live.description_key
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
  source_key = merge.new_source_key,
  description = merge.new_description,
  severity = case
    when flags.severity_source is distinct from 'surface_system' then merge.new_severity
    else flags.severity
  end
from intake_injury_merge merge
where flags.id = merge.id
  and merge.id = merge.keep_id
  and flags.plan_id is distinct from merge.new_plan_id;

drop table intake_injury_merge;
