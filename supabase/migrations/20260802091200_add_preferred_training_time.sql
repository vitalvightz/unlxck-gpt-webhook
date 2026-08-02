-- Optional athlete-selected training time for session-timed coaching pushes.
-- Null means UNLXCK must not guess when the athlete trains.

alter table public.notification_preferences
  add column if not exists preferred_training_time time without time zone;

comment on column public.notification_preferences.preferred_training_time is
  'Optional athlete-local preferred training time. Null disables timed session reminders.';
