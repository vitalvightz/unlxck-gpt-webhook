# Groin strain RESTORE → LOAD: held after targeted review

Decision, 20 October 2026: **LOAD remains unavailable.** This is the requested
closed-stage fallback, not a fifth activated programme. Started from Main
`1315869a9baef178bec86c409852182ca62ba6df`. One scoped generation-boundary fix
keeps guided groin strain on its reviewed baseline; no profile, bank, review,
clearance, editor, database or daily interaction changes are made.

## Presentation considered

The potential indication is a clinician-diagnosed, uncomplicated **acute
adductor muscle strain**, on a known side, with compatible reported severity and
explicit rehabilitation loading permission for the current episode. A generic
groin-strain label or medial pain location does not establish this indication.
Impact bands in the injury editor are not muscle-tear grades.

Hip flexor/iliopsoas injury, inguinal pain/hernia, hip joint/labral pathology,
pubic-related pain, tendon injury/avulsion, significant tearing or functional
loss, neurological/unexplained symptoms, chronic/recurring groin pain and
uncertain/conflicting presentations are outside that proposed indication.
Medical holds, red flags and clinician restrictions always take priority.
No presentation is currently eligible for groin LOAD, including the proposed
narrow indication with reassuring history. Existing baseline routing remains
unchanged; this review does not retrospectively establish the diagnosis or
validate baseline exercises for excluded pathologies.

## Evidence inspected and its limits

This review starts from the groin findings in
[the advanced review](rehab-advanced-candidate-review.md#groin_strain--tier-2)
and [the bank rationalisation](rehab-bank-rationalisation.md). Only groin/adductor
mechanics, resistance, dose and entry requirements were investigated.

- [Serner et al., 2020, full text](https://journals.sagepub.com/doi/full/10.1177/2325967119897247):
  81 adult male athletes with clinically diagnosed acute adductor injuries;
  individual physiotherapist supervision, adjustable resistance and
  pain-controlled exercise. This supports progressive adductor rehabilitation
  in the assessed population, not automatic eligibility from a groin label.
  Its strength, stretch and sport milestones concern later rehabilitation;
  running, sprinting, kicking and Copenhagen milestones are not early LOAD
  entry requirements. Its repetition-maximum approach is unsuitable to copy
  into this unsupervised consumer starter.
- [Thorborg, 2023, full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC10569248/):
  distinguishes muscle, tendon, bone and other groin presentations; supports
  individualized slow strengthening, including limb-weight side-lying work
  and cable/band exercises. Early isometric activation and later load progression
  depend on tissue irritability and clinical reasoning. The conditioning
  discussion does not define a universal cable starting weight, or certify
  resisted-adduction tolerance from unresisted completion. The paper was
  retrieved directly; the PMC browser tool intermittently returned a challenge.
- [NHS sprains and strains](https://www.nhs.uk/conditions/sprains-and-strains/):
  supports protection, comfortable movement and assessment of severe/worsening
  symptoms or loss of function. It supplies neither an adductor diagnosis nor
  a resistance prescription.
- [Berkshire Healthcare NHS, current groin-strain advice](https://www.berkshirehealthcare.nhs.uk/advice/groin-strain),
  with [February 2026 leaflet](https://www.berkshirehealthcare.nhs.uk/media/w13npqcr/bh1165h-groin-strain-v1-feb-2026.pdf):
  offers gentle supine bent-knee squeezes, five-second holds, 10–20 repetitions
  twice daily, alongside bottom-leg lifts and a bridge variation. This is a
  useful simpler initial exercise reference. It does not specify squeeze force
  or establish that a gentle squeeze progresses an athlete beyond the existing
  side-lying adduction.
- [Dynamic Health NHS, adductor strains/tendinopathies](https://www.dynamichealth.nhs.uk/help-and-advice/hip-pain/hip-adductor-strains-and-tendinopathies/):
  includes a seated five-second ball squeeze and side-lying adduction, with
  individualized exercise advice. Its broader muscle/tendon population and
  symptom-guided programme do not resolve the specific progression gap here.

Sources support exercise options and individualized load management. **The
decision to withhold automatic LOAD is a conservative product decision**, not
a research finding that every initial squeeze requires dynamometry, MRI,
maximal testing or a questionnaire. No universal readiness threshold is added.

## Candidate decision and precise blocker

| Option inspected | Useful potential | Why it is not activated |
| --- | --- | --- |
| `groin_strain_standing_cable_adduction` | Slow resisted adduction meaningfully adds external resistance | Existing notes say fixed “light” cable; dose is null. No captured clinician-selected cable load/range or tissue-specific functional tolerance makes that an executable bounded prescription. Equipment access alone supplies none of these. Also needs opposite-leg standing and hand/trunk support suitability. |
| Supine/seated gentle ball or pillow squeeze | Low-complexity, supported initial isometric exercise | Force and object resistance are unspecified. Calling this bodyweight or assigning a known low force would misstate the mechanics. Time/repetition bounds alone do not bound force or establish additional loading beyond RESTORE. It may be an early option; it is not established here as the required meaningful progression. |
| Fixed-tempo side-lying adduction | Can structure time under tension without external equipment | Current RESTORE already lifts/lowers the limb slowly. Repackaging it with a count/tempo does not by itself establish a distinct strengthening progression. Added weight, lever/range change or fatigue progression would need its own review. |

The existing regional squeeze entries are `groin_pain_isometric_squeeze_with_ball`,
`groin_unspecified_isometric_side_lying_squeeze` and
`groin_unspecified_isometric_adductor_squeeze_ball_between_knees`. They lack
reviewed strain-specific indication/resistance/dose and include undefined
mechanics or progressions. They are not silently borrowed across diagnoses.
Bridge, lunge, machine, unstable and standing variants add demands without
solving the entry/loading gaps. Copenhagen, maximal squeezes, wide stretching,
sprinting, cutting, shuffling, explosive kicks and contact work are excluded.

**No LOAD exercise or dose was selected.** Cable identity, dormant metadata and
historical reviews remain unchanged. A new identity cannot supply missing
clinical evidence, so none is created.

## Shared-engine and consumer consequences

All 64 profiles, including groin v1, remain byte-for-byte unchanged. Groin has
only CALM and RESTORE prescriptions, no promotable transition and no registered
groin LOAD option. DYNAMIC and RETURN remain unavailable. This is enforced by
the existing shared engine; no alternate engine or feature flag is introduced.

The current normal flow remains: record injury → supported RESTORE → complete
as shown/modified/skipped → Better/Same/Worse → existing next-day response.
Normal completion can establish exposure and attributable symptom responses;
it cannot establish measured strength, ROM or resisted-adduction tolerance.
Even complete, reassuring RESTORE history plus loading/sport permission leaves
LOAD closed. Contact permission never substitutes for rehabilitation permission
and exercise progression grants no sparring, kicking or contact clearance.

**Zero new occasional answers and zero new daily questions.** A subtype selector
would identify only part of the missing evidence and unlock nothing, so it is
not added. There is no worksheet, timestamp, measurement, new clearance UI or
dashboard. No exercise-specific multi-injury exception is added for an exercise
that cannot be prescribed. Whole-athlete safety and appropriate baseline care
remain in charge; an unrelated minor injury gains no new veto from this PR.

## Verification and scope

`tests/test_groin_load_hold.py` checks the apparent-ready case and ownership,
side/episode, subtype uncertainty/conflicts, severity, medical/restriction,
permission, exposure, response, history and equipment variations. It exercises
normal RESTORE capture, delayed response, Today/generation nonactivation, daily
allocation, a setback, and immutable saved/started/completed baseline history.
It does **not** claim a working LOAD completion or new frozen-LOAD revalidation:
there is no executable LOAD to freeze or complete. Existing frozen-session
regressions and all four activated pilots are run separately.

`tools/rehab_groin_activation_inventory_baseline.json` records the closed outcome
and pins Main's entire pathway file, all profile hashes, full bank and review
ledger, prior activation manifests, dated audit/provenance artifacts and athlete
interaction files. A future activation must deliberately replace these pins
with an exact approved delta; this PR supplies no historical projection or
changes to previous tests. Full validation and CI comparison are recorded in
the PR and [verification record](groin-strain-load-verification.md).

The new end-to-end test also reproduced an inherited Main generation leak:
the area parser left `rehab_type=unspecified` after guided notes resolved
`injury_type=strain`, bypassing the exact groin policy and selecting legacy
unreviewed Copenhagen content. Adding only `groin/strain` to the existing
pilot type-preservation set in `fightcamp/input_parsing.py` makes generation use
the reviewed groin decision. This does not infer an adductor diagnosis, activate
LOAD, or alter the other four programmes. The failing integration test is
retained and passes with that fix.

To reopen, first establish a reviewed, distinct strengthening starter with
honest resistance/dose mechanics and a defensible entry rule using available
inputs. If external resistance remains necessary, it must be individually
selected and attributable through existing reviewed-prescription architecture;
generic permission cannot manufacture it. This is the remaining scoped clinical
decision, not a request to restart the bank audit or add athlete paperwork.
The 64-profile × 5-stage coverage matrix and later pilot stages are outside this PR.
