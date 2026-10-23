# Action hierarchy

Use one dominant action per section. Choose the treatment by what the action does, rather than making every action a bordered button.

| Role | Pattern | Examples |
| --- | --- | --- |
| Next step | Existing `.cta`; full width when it is the section's clear next step | Preview session, Generate Plan, Continue |
| Supporting navigation | `ActionLink` from `web/components/action-link.tsx` | Fight camp, Camp Setup, alternative setup routes |
| Utility | `.action-utility` with an icon and short label | Visualisation, Free timer |
| Preset or setting | `.action-choice` with `aria-pressed` or `aria-checked` when selected | Round formats, timer settings, Quick Build starters |
| Form footer | `.cta` for the next step, `.action-link` for save/back | Save draft + Continue |

Use `.action-stack` to group one primary action with quiet navigation beneath it. Use `.action-alternatives` for a compact row of alternative routes. These are links, so do not use selectable tiles or pressed states. Reserve choice cards for actual selections.

Quiet actions keep at least a 44 × 44 px touch target, visible focus, disabled states and readable contrast. They can have a subtle hover surface, but do not have a persistent border or fill. Keep their text labels visible; icons alone should be reserved for familiar controls with accessible names.

Preset choices use quiet text, a subtle selected surface and a thin underline instead of outlined pills or a primary fill. Preserve selection semantics and descriptions. Keep short format choices in a balanced compact group rather than wrapping into a three-plus-one arrangement. Do not apply this pattern to navigation links or ordinary data labels.

Avoid adding a container around an action group unless it separates content or protects sticky controls from content underneath. A form footer can have a plain opaque backing without an additional outlined card. Preserve the timer's existing phase colours and primary treatment; apply the same hierarchy rather than forcing every primary action to use the same colour.
