# UNLXCK translation context

English (`messages/en.json`) is the single source of truth. Every other catalog is a
translation of it, produced either by hand or by the Azure Translator sync
(`npm run i18n:sync`) and then reviewed against this document.

## What the product is

UNLXCK is a training app for **combat-sports athletes** — boxing, MMA, kickboxing,
Muay Thai, wrestling and grappling. An athlete gives the app their profile and fight
details, and the app generates and maintains a dated training plan that adapts to how
recovered, loaded and injured they are.

Every string in this app is read by a fighter or a coach, in a gym, usually on a phone,
often between rounds. Translate the way a native coach in that sport talks to their
athletes: short, direct, concrete. Prefer the word the sport actually uses in that
language over the dictionary word. Never translate word for word.

## The domain sense of the words that go wrong

These are the terms Azure has mistranslated, because each one is ambiguous in isolation
and the app uses the combat-sports sense, never the everyday one. The machine-readable
form of this list — the preferred term per locale plus the renderings that are treated
as defects — is `i18n/glossary.mjs`, which the sync pipeline sends to Azure as
dictionary hints and which `npm run i18n:check` enforces.

| Term | Sense in this app | Never |
| --- | --- | --- |
| camp, fight camp | the block of preparation leading to a fight — the product's central noun | a campsite / tents / camping |
| round | a timed round of a fight or of bag or pad work | ammunition, a cartridge, a bullet, a lap, a turn, a shift |
| heavy bag | the hanging punchbag in a gym | a heavy suitcase, luggage, a shopping bag |
| drill | a repeated technical exercise | a power drill, a drill bit, boring a hole |
| sparring | controlled practice fighting — an untranslated loanword in all four locales | a real fight, a duel, a bout |
| intake | the athlete's saved questionnaire of profile and fight data | air intake, food intake, hospital admission, enrolment, headcount, a CV |
| readiness | today's self-reported physical readiness to train | willingness, eagerness, being about to do something |
| check-in | the short daily prompt where the athlete reports how they are | hotel or airport check-in |
| settings | the app's configuration screens | scenery, a stage set, scenarios, a landscape |
| focus | which qualities the camp prioritises; a *focus cap* is the maximum number of those that may be selected | camera focus, a physical cap, a hood, a lid |
| session | one training session on the plan | a login session, a browser session, a meeting |
| fight date | the date of the booked fight | a romantic date, a calendar appointment, a dried fruit |
| training load | accumulated physical workload | a cargo load, a file upload, formal education |
| recovery | physical recovery between sessions | data recovery, recovering a lost object, rehab from addiction |
| injury | a physical injury the plan must work around | an insult, damage to property |
| coach | the human coach of the athlete | a bus, a railway carriage, economy class |
| gym | the training gym the athlete belongs to | a school gymnasium, a sports arena, PE class |
| plan | the generated training plan | a blueprint, a floor plan, a phone tariff, a flat surface |
| taper | the deliberate drop in load before the fight | a cone, a narrowing, a candle |
| S&C | strength and conditioning | air conditioning, fuel, shampoo |

## Rules that are not negotiable

1. **Keep every placeholder and its spelling exactly**: `{count}`, `{language}`,
   `{name}`. Do not translate, reorder inside the braces, add spaces, or drop one.
   ICU plural/select syntax keeps its English keywords (`plural`, `one`, `other`).
2. **Keep the key.** Keys are English and never translated.
3. **Keep branding exactly as written**: `UNLXCK`, `Lxcked`, `Advanced Intake`,
   `Quick Build`, `Fight Lab`. These are product names, not words.
4. **Keep HTML entities and punctuation the source needs**: `&rsquo;`, `&amp;`,
   trailing colons, ellipses, the `-` in `2-5 minutes`.
5. **Do not translate athlete-entered content or generated camp-plan content.** Only
   the static interface copy in `messages/*.json` is translated. Plan text that comes
   back from the planner is rendered as the planner produced it.
6. **Do not add a second translation system.** next-intl plus these catalogs plus the
   Azure sync are the whole architecture.

## Per-locale voice

- **es** — Neutral Latin American Spanish. Address the athlete as *tú*. Keep the sport's
  English loanwords the sport itself keeps (`sparring`, `round`, `camp`).
- **pt-BR** — Brazilian Portuguese, *você*. `academia`, never `ginásio`, for a gym.
- **fr** — Address the athlete as *vous*. `séance` for a training session, `sac de
  frappe` for the heavy bag, `affûtage` for the taper.
- **it** — Address the athlete as *tu*. `sacco pesante`, `scarico` for the taper,
  `infortunio` for an injury.

## Preserving human work

A key that has no entry in `messages/.azure-sync-state.json` is human-written or
human-reviewed. The sync never overwrites those, and a review pass must not either
unless the translation is actually wrong.
