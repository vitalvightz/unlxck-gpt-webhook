-- Renewable open plans have no persisted week start dates. Use the same stable
-- calendar anchor as their runtime projection so regenerating a plan does not
-- gain a fresh phase-XP scope merely because the plan UUID changed.

create or replace function public.xp_plan_reward_scope(p_plan_id uuid)
returns text
language sql
stable
security invoker
set search_path = pg_catalog, public
as $$
  select case
    when plan.fight_date is not null then
      'fight:' || plan.fight_date::text
    when lower(coalesce(plan.structured_plan -> 'plan_metadata' ->> 'plan_type', '')) = 'open_ongoing_system'
      and public.xp_open_plan_anchor_date(plan.id) is not null then
      'open-anchor:' || public.xp_open_plan_anchor_date(plan.id)::text
    when first_week.start_date is not null then
      'start:' || first_week.start_date || ':' ||
      lower(coalesce(plan.structured_plan -> 'plan_metadata' ->> 'plan_type', 'plan'))
    else 'plan:' || plan.id::text
  end
  from public.plans as plan
  left join lateral (
    select min(week.item ->> 'start_date') as start_date
    from jsonb_array_elements(
      case
        when jsonb_typeof(plan.structured_plan -> 'weeks') = 'array'
          then plan.structured_plan -> 'weeks'
        else '[]'::jsonb
      end
    ) as week(item)
    where coalesce(week.item ->> 'start_date', '') ~ '^\d{4}-\d{2}-\d{2}$'
  ) as first_week on true
  where plan.id = p_plan_id
$$;

revoke all on function public.xp_plan_reward_scope(uuid)
  from public, anon, authenticated;
grant execute on function public.xp_plan_reward_scope(uuid)
  to service_role;
