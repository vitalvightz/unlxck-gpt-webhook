-- Prevent sequential active-plan switching from becoming a session-XP farm and
-- independently verify every full-week source against persisted completions.
-- Session awards retain their original plan provenance so later completion-row
-- updates cannot rewrite which plan earned historical XP.

alter table public.xp_awards
  add column if not exists source_plan_id uuid;

drop trigger if exists xp_awards_source_plan_immutable on public.xp_awards;

-- Best-effort backfill for pre-hardening session awards. The current production
-- ledger has no such rows, but this keeps other environments upgrade-safe.
update public.xp_awards as award
set source_plan_id = completion.plan_id
from public.session_completions as completion
where award.source_plan_id is null
  and award.action in ('training_logged', 'planned_session_completed')
  and completion.athlete_id = award.athlete_id
  and completion.id::text = split_part(award.idempotency_key, ':', 2);

create index if not exists xp_awards_session_source_plan_idx
  on public.xp_awards (athlete_id, calendar_date, source_plan_id)
  where action in ('training_logged', 'planned_session_completed');

create or replace function public.prevent_xp_source_plan_rewrite()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
begin
  if new.source_plan_id is distinct from old.source_plan_id then
    raise exception 'session XP source plan is immutable'
      using errcode = '23514';
  end if;
  return new;
end;
$$;

create trigger xp_awards_source_plan_immutable
before update of source_plan_id on public.xp_awards
for each row execute function public.prevent_xp_source_plan_rewrite();

create or replace function public.enforce_xp_plan_lock_and_week_completion()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_completion_plan_id uuid;
  v_plan_id uuid;
  v_week_id text;
  v_planned_count integer;
begin
  if new.action in ('training_logged', 'planned_session_completed') then
    select completion.plan_id
      into v_completion_plan_id
    from public.session_completions as completion
    where completion.athlete_id = new.athlete_id
      and completion.id::text = split_part(new.idempotency_key, ':', 2);

    if v_completion_plan_id is null then
      raise exception 'session XP plan source is unavailable' using errcode = '23514';
    end if;

    -- Always derive provenance from the terminal completion. A caller-supplied
    -- source_plan_id is ignored, and the stored value never follows later edits
    -- to that completion row.
    new.source_plan_id := v_completion_plan_id;

    if exists (
      select 1
      from public.xp_awards as previous_award
      where previous_award.athlete_id = new.athlete_id
        and previous_award.calendar_date = new.calendar_date
        and previous_award.action in ('training_logged', 'planned_session_completed')
        and previous_award.source_plan_id is distinct from v_completion_plan_id
    ) then
      raise exception 'session XP is already locked to another plan for this training day'
        using errcode = '23514';
    end if;
  end if;

  if new.action = 'full_training_week_completed' then
    begin
      v_plan_id := split_part(new.idempotency_key, ':', 2)::uuid;
    exception when invalid_text_representation then
      raise exception 'invalid full-week plan source id' using errcode = '22023';
    end;
    v_week_id := btrim(split_part(new.idempotency_key, ':', 3));

    select count(*)
      into v_planned_count
    from public.plans as plan
    cross join lateral jsonb_array_elements(
      case
        when jsonb_typeof(plan.structured_plan -> 'weeks') = 'array'
          then plan.structured_plan -> 'weeks'
        else '[]'::jsonb
      end
    ) as week(item)
    cross join lateral jsonb_array_elements(
      case
        when jsonb_typeof(week.item -> 'days') = 'array'
          then week.item -> 'days'
        else '[]'::jsonb
      end
    ) as day(item)
    cross join lateral jsonb_array_elements(
      case
        when jsonb_typeof(day.item -> 'sessions') = 'array'
          then day.item -> 'sessions'
        else '[]'::jsonb
      end
    ) as session(item)
    where plan.id = v_plan_id
      and plan.athlete_id = new.athlete_id
      and week.item ->> 'week_id' = v_week_id
      and week.item ->> 'start_date' = new.calendar_date::text
      and lower(coalesce(day.item ->> 'day_type', '')) <> 'rest'
      and nullif(btrim(session.item ->> 'session_id'), '') is not null;

    if coalesce(v_planned_count, 0) = 0 then
      raise exception 'full-week XP source has no planned sessions'
        using errcode = '23514';
    end if;

    if exists (
      select 1
      from public.plans as plan
      cross join lateral jsonb_array_elements(
        case
          when jsonb_typeof(plan.structured_plan -> 'weeks') = 'array'
            then plan.structured_plan -> 'weeks'
          else '[]'::jsonb
        end
      ) as week(item)
      cross join lateral jsonb_array_elements(
        case
          when jsonb_typeof(week.item -> 'days') = 'array'
            then week.item -> 'days'
          else '[]'::jsonb
        end
      ) as day(item)
      cross join lateral jsonb_array_elements(
        case
          when jsonb_typeof(day.item -> 'sessions') = 'array'
            then day.item -> 'sessions'
          else '[]'::jsonb
        end
      ) as session(item)
      where plan.id = v_plan_id
        and plan.athlete_id = new.athlete_id
        and week.item ->> 'week_id' = v_week_id
        and week.item ->> 'start_date' = new.calendar_date::text
        and lower(coalesce(day.item ->> 'day_type', '')) <> 'rest'
        and nullif(btrim(session.item ->> 'session_id'), '') is not null
        and not exists (
          select 1
          from public.session_completions as completion
          where completion.athlete_id = new.athlete_id
            and completion.plan_id = v_plan_id
            and completion.session_id = session.item ->> 'session_id'
            and completion.training_day::text = day.item ->> 'date'
            and completion.status in ('done', 'modified')
        )
    ) then
      raise exception 'full-week XP requires every planned session to be completed or modified'
        using errcode = '23514';
    end if;
  end if;

  return new;
end;
$$;

drop trigger if exists xp_awards_plan_lock_and_week_completion on public.xp_awards;
create trigger xp_awards_plan_lock_and_week_completion
before insert on public.xp_awards
for each row execute function public.enforce_xp_plan_lock_and_week_completion();

create or replace function public.validate_xp_abuse_hardening()
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
begin
  if coalesce(auth.role(), '') <> 'service_role' then
    raise exception 'validate_xp_abuse_hardening is restricted to the backend service role'
      using errcode = '42501';
  end if;

  if to_regclass('public.xp_awards_one_time_action_per_athlete') is null
    or to_regclass('public.xp_awards_one_daily_action_per_athlete') is null
    or not exists (
      select 1 from information_schema.columns
      where table_schema = 'public'
        and table_name = 'xp_awards'
        and column_name = 'source_plan_id'
    )
    or not exists (
      select 1 from pg_trigger
      where tgrelid = 'public.xp_awards'::regclass
        and tgname = 'xp_awards_source_integrity'
        and not tgisinternal
    )
    or not exists (
      select 1 from pg_trigger
      where tgrelid = 'public.xp_awards'::regclass
        and tgname = 'xp_awards_plan_lock_and_week_completion'
        and not tgisinternal
    )
    or not exists (
      select 1 from pg_trigger
      where tgrelid = 'public.xp_awards'::regclass
        and tgname = 'xp_awards_source_plan_immutable'
        and not tgisinternal
    ) then
    raise exception 'XP abuse hardening is incomplete' using errcode = '55000';
  end if;

  return jsonb_build_object('ok', true, 'version', '20260803181000');
end;
$$;

revoke all on function public.prevent_xp_source_plan_rewrite()
  from public, anon, authenticated;
grant execute on function public.prevent_xp_source_plan_rewrite()
  to service_role;

revoke all on function public.enforce_xp_plan_lock_and_week_completion()
  from public, anon, authenticated;
grant execute on function public.enforce_xp_plan_lock_and_week_completion()
  to service_role;

revoke all on function public.validate_xp_abuse_hardening()
  from public, anon, authenticated;
grant execute on function public.validate_xp_abuse_hardening()
  to service_role;
