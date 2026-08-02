-- Evaluate auth.uid() once per statement instead of once per row, and scope the
-- policies explicitly to authenticated browser sessions. Writes remain service-
-- role-only through grants and the backend APIs.

drop policy if exists "notification_preferences_owner_select"
  on public.notification_preferences;
create policy "notification_preferences_owner_select"
  on public.notification_preferences
  for select
  to authenticated
  using ((select auth.uid()) = profile_id);

drop policy if exists "notification_deliveries_owner_select"
  on public.notification_deliveries;
create policy "notification_deliveries_owner_select"
  on public.notification_deliveries
  for select
  to authenticated
  using ((select auth.uid()) = profile_id);
