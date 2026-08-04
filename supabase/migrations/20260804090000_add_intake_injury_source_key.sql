-- Stable identity for intake-seeded injury flags.
--
-- Existing rows are adopted before the uniqueness constraint is applied:
-- * one canonical row keeps its existing status and resolved_at;
-- * pre-existing duplicates are retained as resolved audit rows with distinct
--   duplicate source keys;
-- * future reads use one transaction-scoped RPC to adopt or insert atomically.
alter table public.injury_flags
  add column if not exists source_key text;

-- Backfill deterministic source keys for legacy intake rows. The hash algorithm
-- mirrors api/services/intake_injury_sync.py:
--   normalized body area + newline + normalized description.
with legacy as (
  select
    id,
    athlete_id,
    'intake:' || plan_id::text || ':' ||
      left(
        encode(
          digest(
            replace(
              replace(
                replace(lower(btrim(coalesce(body_area, ''))), '-', '_'),
                '/',
                '_'
              ),
              ' ',
              '_'
            )
            || chr(10) ||
            regexp_replace(
              lower(btrim(coalesce(description, ''))),
              '\s+',
              ' ',
              'g'
            ),
            'sha256'
          ),
          'hex'
        ),
        24
      ) as deterministic_key,
    row_number() over (
      partition by
        athlete_id,
        plan_id,
        replace(
          replace(
            replace(lower(btrim(coalesce(body_area, ''))), '-', '_'),
            '/',
            '_'
          ),
          ' ',
          '_'
        ),
        regexp_replace(
          lower(btrim(coalesce(description, ''))),
          '\s+',
          ' ',
          'g'
        )
      order by
        case lower(btrim(coalesce(status, '')))
          when 'resolved' then 0
          when 'monitoring' then 1
          when 'open' then 2
          else 3
        end,
        resolved_at desc nulls last,
        created_at asc,
        id asc
    ) as row_rank
  from public.injury_flags
  where source = 'intake'
    and plan_id is not null
    and source_key is null
),
ranked as (
  select
    legacy.*,
    exists (
      select 1
      from public.injury_flags existing
      where existing.athlete_id = legacy.athlete_id
        and existing.source_key = legacy.deterministic_key
    ) as key_already_exists
  from legacy
)
update public.injury_flags flags
set
  source_key = ranked.deterministic_key || ':legacy-duplicate:' || flags.id::text,
  status = 'resolved',
  resolved_at = coalesce(flags.resolved_at, now())
from ranked
where flags.id = ranked.id
  and (ranked.key_already_exists or ranked.row_rank > 1);

-- Attach the deterministic key to the remaining canonical legacy row. Its
-- status and resolved_at are intentionally untouched.
with legacy as (
  select
    id,
    athlete_id,
    'intake:' || plan_id::text || ':' ||
      left(
        encode(
          digest(
            replace(
              replace(
                replace(lower(btrim(coalesce(body_area, ''))), '-', '_'),
                '/',
                '_'
              ),
              ' ',
              '_'
            )
            || chr(10) ||
            regexp_replace(
              lower(btrim(coalesce(description, ''))),
              '\s+',
              ' ',
              'g'
            ),
            'sha256'
          ),
          'hex'
        ),
        24
      ) as deterministic_key,
    row_number() over (
      partition by
        athlete_id,
        plan_id,
        replace(
          replace(
            replace(lower(btrim(coalesce(body_area, ''))), '-', '_'),
            '/',
            '_'
          ),
          ' ',
          '_'
        ),
        regexp_replace(
          lower(btrim(coalesce(description, ''))),
          '\s+',
          ' ',
          'g'
        )
      order by
        case lower(btrim(coalesce(status, '')))
          when 'resolved' then 0
          when 'monitoring' then 1
          when 'open' then 2
          else 3
        end,
        resolved_at desc nulls last,
        created_at asc,
        id asc
    ) as row_rank
  from public.injury_flags
  where source = 'intake'
    and plan_id is not null
    and source_key is null
)
update public.injury_flags flags
set source_key = legacy.deterministic_key
from legacy
where flags.id = legacy.id
  and legacy.row_rank = 1
  and not exists (
    select 1
    from public.injury_flags existing
    where existing.athlete_id = legacy.athlete_id
      and existing.source_key = legacy.deterministic_key
  );

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'injury_flags_athlete_source_key_key'
      and conrelid = 'public.injury_flags'::regclass
  ) then
    alter table public.injury_flags
      add constraint injury_flags_athlete_source_key_key
      unique (athlete_id, source_key);
  end if;
end
$$;

create or replace function public.adopt_or_create_intake_injury_flag(
  p_athlete_id uuid,
  p_plan_id uuid,
  p_source_key text,
  p_body_area text,
  p_description text,
  p_severity text default 'moderate',
  p_status text default 'open',
  p_resolved_at timestamptz default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_flag public.injury_flags%rowtype;
  v_now timestamptz := now();
begin
  if nullif(btrim(p_source_key), '') is null then
    raise exception 'missing_intake_injury_source_key'
      using errcode = '22023';
  end if;

  if p_plan_id is null then
    raise exception 'missing_intake_injury_plan_id'
      using errcode = '22023';
  end if;

  -- Serialize all adoption/creation attempts for this athlete + source identity.
  perform pg_advisory_xact_lock(
    hashtextextended(p_athlete_id::text || ':' || p_source_key, 0)
  );

  select *
  into v_flag
  from public.injury_flags
  where athlete_id = p_athlete_id
    and source_key = p_source_key
  limit 1
  for update;

  if found then
    -- Clean up any leftover unkeyed duplicates without altering the canonical
    -- row's status or resolved timestamp.
    update public.injury_flags
    set
      source_key = p_source_key || ':legacy-duplicate:' || id::text,
      status = 'resolved',
      resolved_at = coalesce(resolved_at, v_now)
    where athlete_id = p_athlete_id
      and plan_id = p_plan_id
      and source = 'intake'
      and source_key is null
      and replace(
        replace(
          replace(lower(btrim(coalesce(body_area, ''))), '-', '_'),
          '/',
          '_'
        ),
        ' ',
        '_'
      ) = replace(
        replace(
          replace(lower(btrim(coalesce(p_body_area, ''))), '-', '_'),
          '/',
          '_'
        ),
        ' ',
        '_'
      )
      and regexp_replace(
        lower(btrim(coalesce(description, ''))),
        '\s+',
        ' ',
        'g'
      ) = regexp_replace(
        lower(btrim(coalesce(p_description, ''))),
        '\s+',
        ' ',
        'g'
      );

    return to_jsonb(v_flag);
  end if;

  -- Prefer a resolved legacy row so an athlete's previous clear action wins
  -- over any duplicate open row from the same intake/plan identity.
  select *
  into v_flag
  from public.injury_flags
  where athlete_id = p_athlete_id
    and plan_id = p_plan_id
    and source = 'intake'
    and source_key is null
    and replace(
      replace(
        replace(lower(btrim(coalesce(body_area, ''))), '-', '_'),
        '/',
        '_'
      ),
      ' ',
      '_'
    ) = replace(
      replace(
        replace(lower(btrim(coalesce(p_body_area, ''))), '-', '_'),
        '/',
        '_'
      ),
      ' ',
      '_'
    )
    and regexp_replace(
      lower(btrim(coalesce(description, ''))),
      '\s+',
      ' ',
      'g'
    ) = regexp_replace(
      lower(btrim(coalesce(p_description, ''))),
      '\s+',
      ' ',
      'g'
    )
  order by
    case lower(btrim(coalesce(status, '')))
      when 'resolved' then 0
      when 'monitoring' then 1
      when 'open' then 2
      else 3
    end,
    resolved_at desc nulls last,
    created_at asc,
    id asc
  limit 1
  for update;

  if found then
    -- Preserve the canonical row exactly. Resolve other live duplicates and give
    -- them distinct audit keys so the uniqueness constraint remains valid.
    update public.injury_flags
    set
      source_key = p_source_key || ':legacy-duplicate:' || id::text,
      status = 'resolved',
      resolved_at = coalesce(resolved_at, v_now)
    where athlete_id = p_athlete_id
      and plan_id = p_plan_id
      and source = 'intake'
      and source_key is null
      and id <> v_flag.id
      and replace(
        replace(
          replace(lower(btrim(coalesce(body_area, ''))), '-', '_'),
          '/',
          '_'
        ),
        ' ',
        '_'
      ) = replace(
        replace(
          replace(lower(btrim(coalesce(p_body_area, ''))), '-', '_'),
          '/',
          '_'
        ),
        ' ',
        '_'
      )
      and regexp_replace(
        lower(btrim(coalesce(description, ''))),
        '\s+',
        ' ',
        'g'
      ) = regexp_replace(
        lower(btrim(coalesce(p_description, ''))),
        '\s+',
        ' ',
        'g'
      );

    update public.injury_flags
    set source_key = p_source_key
    where id = v_flag.id
    returning * into v_flag;

    return to_jsonb(v_flag);
  end if;

  insert into public.injury_flags (
    athlete_id,
    plan_id,
    source,
    source_key,
    body_area,
    description,
    severity,
    status,
    resolved_at
  )
  values (
    p_athlete_id,
    p_plan_id,
    'intake',
    p_source_key,
    coalesce(p_body_area, ''),
    coalesce(p_description, ''),
    coalesce(nullif(lower(btrim(p_severity)), ''), 'moderate'),
    coalesce(nullif(lower(btrim(p_status)), ''), 'open'),
    p_resolved_at
  )
  on conflict (athlete_id, source_key) do nothing
  returning * into v_flag;

  if not found then
    select *
    into v_flag
    from public.injury_flags
    where athlete_id = p_athlete_id
      and source_key = p_source_key
    limit 1;
  end if;

  return to_jsonb(v_flag);
end;
$$;

revoke all on function public.adopt_or_create_intake_injury_flag(
  uuid,
  uuid,
  text,
  text,
  text,
  text,
  text,
  timestamptz
) from public, anon, authenticated;

grant execute on function public.adopt_or_create_intake_injury_flag(
  uuid,
  uuid,
  text,
  text,
  text,
  text,
  text,
  timestamptz
) to service_role;
