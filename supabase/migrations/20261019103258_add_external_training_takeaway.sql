-- A manual session's optional takeaway: what the athlete wants to remember
-- (PUT /api/training/sessions/{id}/takeaway).
--
-- It is written on its own, outside the create fingerprint and the
-- activity/duration/effort edit, so a retried create or an edit never clears
-- it. It is reflection only: no workload, XP, readiness or rehab reads it.
--
-- Repeatable: every step is guarded.

alter table public.external_training_sessions
  add column if not exists takeaway text not null default '';

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'external_training_sessions_takeaway_length'
      and conrelid = 'public.external_training_sessions'::regclass) then
    alter table public.external_training_sessions
      add constraint external_training_sessions_takeaway_length check (char_length(takeaway) <= 280);
  end if;
end $$;
