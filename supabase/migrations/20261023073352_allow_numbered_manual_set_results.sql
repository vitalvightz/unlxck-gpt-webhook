-- Match exercise_logs.actual's bound for up to 50 numbered set results with RPE.
begin;
alter table public.manual_exercise_entries
  drop constraint if exists manual_exercise_entries_actual_check;
alter table public.manual_exercise_entries
  add constraint manual_exercise_entries_actual_check
  check (jsonb_typeof(actual) = 'object' and octet_length(actual::text) <= 8192);
commit;
