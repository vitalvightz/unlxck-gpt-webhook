-- Normalize legacy plan statuses so future row updates satisfy plans_status_check.
-- Safe to run more than once.

update public.plans
set status = case
  when status is null or btrim(status) = '' then 'generated'
  when lower(btrim(status)) in (
    'generated',
    'ready',
    'review_required',
    'held_for_review',
    'publishable_with_flags',
    'triage_blocked',
    'medical_hold',
    'restricted_rehab_only',
    'needs_review',
    'archived'
  ) then lower(btrim(status))
  else 'review_required'
end
where status is null
   or status <> lower(btrim(status))
   or lower(btrim(status)) not in (
    'generated',
    'ready',
    'review_required',
    'held_for_review',
    'publishable_with_flags',
    'triage_blocked',
    'medical_hold',
    'restricted_rehab_only',
    'needs_review',
    'archived'
   );
