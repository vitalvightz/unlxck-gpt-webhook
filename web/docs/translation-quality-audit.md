# Translation quality audit of PR #2546

PR #2546 localised the whole interface by sending each English UI string to Azure
Translator on its own. With no surrounding sentence, Azure repeatedly chose the everyday
sense of a word where the app means the combat-sports one. This is the record of what was
wrong, what was repaired, and what is still open.

## What was clearly wrong

Machine output, all four locales, against 2,124 keys per locale.

| Term | What Azure produced | Keys affected |
| --- | --- | --- |
| camp / fight camp | `campamento`, `acampamento`, `camping`, `campo` — a campsite | 238 |
| intake | `admisión`, `ingesta`, `entrada de ar`, `turma`, `effectifs`, `groupe d'accueil`, `apport`, `aspirazione`, `accoglienza`, `reclutamento` — air intake, food intake, hospital admission, a headcount | 168 |
| training | `formación`, `formação`, `formation`, `formazione` — schooling | 53 |
| resume | `currículum`, `currículo`, `CV`, `curriculum` — a résumé, where the app means "continue" | 43 |
| round | `munición`, `cartouche`, `proyectil`, `rodada`, `manche`, `turno`, `giro` — ammunition, a lap, a shift | 33 |
| sparring | `combate`, `combat`, `combattimento` — a real fight | 29 |
| save / saved | `risparmiare`, `economizar`, `économiser`, `ahorrado` — economising | 27 |
| coach | `vagón`, `vagão`, `autocar`, `pullman`, `ônibus` — a bus, a railway carriage | 20 |
| plan | `plano`, `forfait` — a blueprint, a phone tariff | 20 |
| feedback | `retroalimentación`, `ID de retour de larmes` — "tears" | 9 |
| settings | `Escenarios`, `Cenários`, `Décors`, `Cenário…` — scenery, a stage set | 8 |
| injury | `herida`, `ferita` — an open wound | 7 |
| focus (cap) | `Cappuccio di messa a fuoco`, `Capsule de mise au point` — a camera-lens cap | 5 |
| taper | `conicidad`, `conicité`, `afunilamento` — a cone | 3 |
| drill | `taladro`, `broca`, `furadeira` — a power tool | 2 |
| heavy bag | `Munición de sacos pesados`, `sac lourd` | 2 |
| gym | `ginásio`, `gymnase` — a sports arena, a school gym | 2 |
| walking-around weight | `giro di camminata`, `faire le tour de la maison` — a stroll | 2 |
| S&C | `la pression et le carburant` — pressure and fuel | 1 |

Counted across the four locales together. By locale, the number of keys carrying at least
one defect was es 218, pt-BR 155, it 142, fr 134.

Separately, product names were translated away, which the glossary now also refuses:

- `UNLXCK Your Potential` → `¡Increíble tu potencial`, `Incrível Seu Potencial`,
  `Incroyable ton potentiel` — the brand read as the word "unlock".
- `Quick Build` → `Construção Rápida`, `construction rapide`, `Costruzione rapida`,
  `Build Rápida` (37 keys).
- `Advanced Intake` → `Admisión Avanzada`, `Admissão Avançada`, `Ingresso Avanzato`,
  `convocatoria avanzada`, `Questionnaire complète avancée` (39 keys).
- `Lxcked in.` → fr `Immatriculé.` — "registered", as in a vehicle.

And two strings had their meaning inverted rather than merely mistermed:

- "Withdrawing stops UNLXCK using your health information…" became "impide que **no
  uses** tu información" / "impede que **você use**" — the brand dropped and the subject
  changed to the athlete.
- it `Detenuti e revisioni dei piani` for "Held & review plans" — *detenuti* is prisoners.

766 strings were rewritten in total: es 245, fr 185, pt-BR 174, it 162.

One human-written string was wrong and was changed: it `Il tuo camp. Bloccato dentro.`
read as "locked inside". It now matches the pt-BR and es taglines: `Focus totale.`

## Which translations are human-written and were preserved

Taken from `messages/.azure-sync-state.json`: a key with no entry there was never
machine-translated.

| Locale | Human-written keys before this pass |
| --- | --- |
| es | 14 (Navigation, PublicHome hero and lead, Auth entry) |
| pt-BR | 14 (same set) |
| it | 202 (the whole pre-PR Italian catalog) |
| fr | 0 — fr was machine-generated in its entirety by an earlier PR |

All of them were kept as written, except the one Italian tagline above and the brand
standardisation of `Unlxck Your Potential` in the it motto. Repaired strings have had
their sync-state entry removed, which is how this repo marks a translation as
human-reviewed: `npm run i18n:sync` will not overwrite them again.

## Untranslated literals that remained after PR #2546

The extractor in PR #2546 only reaches JSX text, a fixed list of JSX attributes, and
string literals in JSX conditional expressions. It does not see values in `||`/`??`
fallbacks, inside template literals, or in conditionals outside JSX, so those reached
production as English on every locale. A scan of `app/` and `components/` found 386
distinct such strings, including every example named in the audit request:

- `"Not set"`, `"Not provided"`, `"Not selected"`, `"Not configured"`, `"Not recorded"`,
  `"Not derived yet"`, `"None recorded"`, `"None logged"`, `"No active plan"`
- `` `${selectedCount} selected` ``, `` `Select archived (${n})` ``,
  `` `Delete selected${…}` ``, `` `Delete archived${…}` ``
- `"Untitled plan"`, `"Unavailable"`, `"Automatic"`, `"Athlete profile"`,
  `"Your progress"`, `"Nutrition workspace"`, `"No athlete email"`,
  `"Unassigned athlete"`, `"Unknown device"`, `"Unknown browser"`, `"Unknown page"`,
  `"Email unavailable"`, `"Authenticated user"`, `"Not connected"`, `"Pick a stronger
  password."`, and the nutrition/admin table labels around them

46 of these are now localised in all five catalogs and wired into the components. The
remainder — roughly 340 distinct strings, mostly per-screen error messages ("Unable to
load plan.", "Unable to save draft.") and the plan-renderer's own labels, concentrated in
`components/plan-viewer.tsx`, `components/plan-intake-form.tsx` and
`components/structured-plan-renderer.tsx` — is not covered here. Closing it means
extending `scripts/i18n-extract-ui.mjs` to the three missing literal positions and
running `npm run i18n:sync`, which now sends the glossary to Azure with every batch.

`scripts/i18n-glossary-check.mjs` holds the list of English phrases that must never
appear on a non-English locale, and `npm run test:i18n` fails if one does.

## A separate English-side defect, not fixed here

The extractor copies JSX text verbatim, so HTML entities went into `en.json` as
entities: `Nutrition &amp; Weight`, `Track today&apos;s injuries`,
`We&rsquo;ll notify you`. Nothing decodes them on the way out of next-intl, so English
renders `Nutrition &amp; Weight` literally. 17 keys are affected. The translations mostly
dropped the entity and read correctly, so this is an English-only bug. Fixing it changes
the hashed key of every affected string, so it is left for its own change.
