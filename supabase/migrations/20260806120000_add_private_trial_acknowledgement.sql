-- Private trial onboarding acknowledgement.
--
-- Testers are shown the private trial instructions once, between account
-- creation and onboarding, and must confirm they understand before continuing.
-- The acknowledgement lives on the profile rather than in browser storage so
-- the gate survives a device change, a reinstall, and a cleared cache — a
-- tester who never saw the instructions is exactly the problem this fixes.

alter table public.profiles
  add column if not exists private_trial_ack_at timestamptz;

comment on column public.profiles.private_trial_ack_at is
  'UTC timestamp at which the athlete confirmed they read the private trial instructions. Null until acknowledged.';
