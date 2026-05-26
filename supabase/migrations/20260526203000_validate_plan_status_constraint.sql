-- Existing plan statuses have been normalized; make the constraint fully valid.

alter table public.plans validate constraint plans_status_check;
