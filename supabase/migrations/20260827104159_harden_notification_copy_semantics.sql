-- Keep production notification copy truthful to the evidence that triggered it.
-- These are copy-only corrections; no intent, preference, cap or delivery schema changes.

with audited_copy(intent, variant_id, title_template, body_template) as (
  values
    ('high_pain_followup', 'hp-01', 'HOW DID YOUR BODY SETTLE?', 'Recent pain was high. Check in before we decide today''s load.'),
    ('high_pain_followup', 'hp-04', 'BODY FIRST. THEN THE WORK.', 'Check in now. Recent high pain changes today''s call.'),
    ('high_pain_followup', 'hp-05', 'HIGH PAIN NEEDS A FRESH READ.', 'Tell me what settled and what did not before today''s load is set.'),
    ('high_pain_followup', 'hp-06', 'FRESH READ. THEN DECIDE.', 'Check in now. Recent high pain changes how we approach today.'),
    ('recovery_checkin', 'rc-01', 'RECOVERY CHECK.', 'Sleep, soreness, pain. Give me the morning read.'),
    ('recovery_nudge', 'rn-05', 'ABSORB THE LOAD.', 'Eat, hydrate, move lightly and let the body recover.'),
    ('recovery_nudge', 'rn-06', 'KEEP TODAY LIGHT.', 'Recover with intent. Don''t turn rest into another session.'),
    ('fight_countdown', 'fc-d01', 'D-1. READY.', 'No chasing fitness now. Stay calm and follow the plan.')
)
update public.notification_templates as templates
set
  title_template = audited_copy.title_template,
  body_template = audited_copy.body_template,
  updated_at = timezone('utc'::text, now())
from audited_copy
where templates.intent = audited_copy.intent
  and templates.variant_id = audited_copy.variant_id
  and templates.locale = 'en-GB'
  and templates.template_version = 1;
