-- Workflow starts that existing records cannot evidence. A saved check-in or
-- sparring log proves completion; only an observed start makes abandonment
-- measurable. Both are optional (consent-gated), non-meaningful and capped at
-- one per athlete per UTC day. No answers, ratings or health values are stored.
alter table public.product_events drop constraint product_events_event_name_check;
alter table public.product_events add constraint product_events_event_name_check check (event_name in (
 'plan_opened','plan_editor_opened','plan_edited','plan_replaced',
 'timer_started','timer_round_completed','timer_completed','timer_exited',
 'history_opened','nutrition_opened','nutrition_saved','feedback_prompt_shown',
 'checkin_started','sparring_log_started',
 'operation_failed','frontend_error'));

drop index public.product_event_discovery_daily;
create unique index product_event_discovery_daily on public.product_events
(athlete_id,event_name,feature,(coalesce(flow_id,'00000000-0000-0000-0000-000000000000'::uuid)),((created_at at time zone 'UTC')::date))
where event_name in ('plan_opened','plan_editor_opened','history_opened','nutrition_opened','nutrition_saved','plan_edited','plan_replaced',
 'checkin_started','sparring_log_started');
