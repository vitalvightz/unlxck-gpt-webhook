-- D-3 / D-1 copy is versioned so production selection is auditable.
-- Delivery eligibility remains server-owned: only the currently active combat
-- plan with a persisted bout date may reach these variants.

update public.notification_templates
set active = false,
    updated_at = timezone('utc'::text, now())
where intent = 'fight_countdown'
  and locale = 'en-GB'
  and variant_id in ('fc-d03', 'fc-d01')
  and template_version < 2;

insert into public.notification_templates (
    intent,
    variant_id,
    title_template,
    body_template,
    locale,
    template_version,
    active,
    selection_weight,
    minimum_timing_confidence
)
values
    (
        'fight_countdown',
        'fc-d03',
        'D-3. FRESHNESS WINS NOW.',
        'No added conditioning, extra rounds or fatigue. Touch the sharpness, then leave it.',
        'en-GB',
        2,
        true,
        1,
        'low'
    ),
    (
        'fight_countdown',
        'fc-d01',
        'D-1. THE WORK IS DONE. KEEP TODAY LIGHT',
        'and sharp. No extra conditioning or unnecessary rounds. Follow your coach''s plan.',
        'en-GB',
        2,
        true,
        1,
        'low'
    )
on conflict (intent, variant_id, locale, template_version)
do update set
    title_template = excluded.title_template,
    body_template = excluded.body_template,
    active = excluded.active,
    selection_weight = excluded.selection_weight,
    minimum_timing_confidence = excluded.minimum_timing_confidence,
    updated_at = timezone('utc'::text, now());
