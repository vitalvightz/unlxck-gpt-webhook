-- Exercise-bank names that are the same movement as an existing demo video,
-- differing only in wording or a non-technical qualifier. Each alias points the
-- bank name at that video (aliases never override another row's primary key).
-- Variants that change execution (stick landing, max height, isometric holds
-- vs dynamic, different equipment) are deliberately left without an alias.

update public.exercise_media m
set aliases = (select array(select distinct unnest(m.aliases || v.extra) order by 1)),
    updated_at = now()
from (values
 ('easy-assault-bike', array['assault-bike']),
 ('band-resisted-straight-punch', array['band-resisted-punch']),
 ('bird-dog-hold', array['bird-dog-hold-only', 'bird-dog-iso-hold']),
 ('brettzel-stretch', array['brettzel-stretch-with-breathing']),
 ('dead-bug-isometric', array['dead-bug-isometric-hold-90-90-position', 'dead-bug-isometric-hold-knees-at-90']),
 ('adductor-squeeze-isometric', array['isometric-adductor-squeeze-ball-between-knees']),
 ('kettlebell-swing', array['kettlebell-swing-hinge-pattern-focus']),
 ('ab-wheel-rollout-kneeling', array['kneeling-rollout-ab-wheel-sliders']),
 ('read-and-counter-flow', array['mma-read-and-counter-flow']),
 ('med-ball-rotational-slam', array['med-ball-slam-rotational']),
 ('nordic-hamstring-curl', array['nordic-hamstring-curl-eccentrics']),
 ('pallof-press-band', array['pallof-press-light-band']),
 ('isometric-pallof-hold', array['pallof-press-isometric-hold']),
 ('plate-pinch-carry', array['pinch-plate-carry-thick-plate']),
 ('foam-roller-thoracic-extension', array['seated-thoracic-extension-over-foam-roller']),
 ('single-leg-balance-eyes-closed', array['single-leg-balance-with-eyes-closed']),
 ('single-leg-bridge-hold', array['single-leg-hip-bridge-hold']),
 ('single-leg-wall-sit-60', array['single-leg-isometric-wall-sit-60-flexion']),
 ('sled-push', array['sled-push-light']),
 ('stir-the-pot', array['stir-the-pot-swiss-ball', 'stir-the-pot-forearms-on-swiss-ball']),
 ('trx-row', array['suspended-row-trx-or-rings']),
 ('wall-bicep-isometric', array['wall-bicep-isometric-straight-arm']),
 ('wrist-roller', array['wrist-roller-light-plate']),
 ('dead-hang', array['post-session-dead-hang-20s']),
 ('band-pull-aparts', array['standing-resistance-band-pull-aparts', 'gentle-band-pull-aparts']),
 ('anti-rotation-press', array['standing-anti-rotation-press']),
 ('band-face-pull', array['face-pull'])
) as v(key, extra)
where m.exercise_key = v.key;
