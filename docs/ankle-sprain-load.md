# Ankle sprain: bounded seated LOAD starter

Inspected merged Main `2ffcf802` (#2814) before implementation. This changes one
profile, ankle_sprain v4 → v5, using the existing progression and permission
contracts. No migration, assessment protocol, new episode event or clinical
verification record is introduced.

## Supported presentation

An active, side-specific, mild ankle sprain that the athlete reports their
clinician described as an uncomplicated outer/lateral ankle sprain. The answer
is recorded once in the existing injury editor, defaults to Not sure, and does
not diagnose ligament damage, identify injury grade or verify fracture exclusion.
An outside-pain description alone is insufficient. Existing unknown records
remain conservative; explicit other presentations use Recovery monitoring.

Medial/deltoid, high/syndesmotic, severe, unstable, recurrent/giving-way,
structural/fracture and neurological concerns are excluded. Known contrary
information takes priority over the subtype answer. Existing medical gates and
red flags remain authoritative. Another active lower-leg/foot episode holds
this bilateral option because one episode's permission cannot cover both feet.
No broad ankle pain, swelling or tightness pathway is activated.

## Evidence and limits

- [JOSPT/APTA 2021 clinical practice guideline](https://www.jospt.org/doi/10.2519/jospt.2021.0302):
  supports protected movement, progressive weight bearing and structured exercise
  tailored to severity and impairments. It does not establish a universal app
  LOAD threshold. Standing capacity and impairment measurements remain unknown.
- [Oxford University Hospitals ankle-sprain guidance](https://www.ouh.nhs.uk/media/i0ldiecy/116454sprain.pdf),
  October 2025: describes chair-seated heel raises with feet flat and slow
  lowering, and advises assessment when pain, swelling or function do not recover.
- [Bexley NHS ankle-sprain guidance](https://msk-bexley.nhs.uk/conditions/foot-and-ankle-pain/ankle-sprain):
  describes comfortable seated heel raises, ten repetitions, twice daily.
  The app caps this at one set once daily with no added resistance or automated
  range increase. Those caps and the mild-only population are product limits,
  not validated clinical readiness criteria. Its more advanced band/balance work
  is not activated; band-circle resistance and foam balance need more capacity
  information than this workflow supplies.
- [Wagemans et al. systematic review](https://pmc.ncbi.nlm.nih.gov/articles/PMC8824326/):
  supports exercise rehabilitation for recurrence reduction, with uncertainty
  about optimal exercise content and dosage. It does not validate this precise
  app prescription or a session-count/time-based transition.
- [PAASS consensus](https://bjsm.bmj.com/content/55/22/1270): informs eventual
  return-to-sport domains. It is not used as a validated early LOAD threshold.
  DYNAMIC and RETURN stay closed.

The existing RESTORE pair contains supported standing balance and heel lowering.
It remains unchanged. The new seated option does **not** claim a greater force
than every RESTORE task: LOAD means eligibility for this bounded strengthening
prescription within reported permission, not a measured improvement in capacity.
No measured ROM, strength, stability or weight-bearing tolerance is inferred.

## Prescription

`ankle_sprain_seated_bilateral_heel_raise`: seated controlled ankle heel raises,
both feet on the floor, front of feet supported, stable chair, comfortable range,
slow raise and lower. **1 × 10, maximum once daily.** No weights, bands, knee
pressure, step, forced range or automatic increase. Stop for pain or worsening
during/after exercise and follow clinician restrictions. Medical assessment
remains appropriate for inability to bear weight, bony tenderness, deformity,
altered sensation, severe swelling, instability or loss of function.

## Eligibility and integration

The shared stage engine must pass: current supported episode and side, explicit
versioned rehabilitation loading/sport-specific permission, reviewed RESTORE
exposure performed as shown, injury-attributable non-worsening during response,
non-worsening next-day response, complete history, no unresolved setback, current
restrictions and available reviewed content/equipment. Contact clearance supplies
none of these. A Better response, permission, elapsed time or completion alone
cannot open LOAD. Unknowns remain unknown.

Today and generation consume the same owned episode observations and exposures.
Today uses the existing cadence, daily allocation and normal session completion.
The existing equipment setup can record chair availability; full-gym presets do
not assume it. LOAD has priority over the preserved RESTORE pair when all gates
pass. Downgrades, missing responses, setbacks or missing equipment invalidate
incompatible unstarted work; started/completed snapshots remain historical.

## Interaction count

| Interaction | Before | After |
| --- | ---: | ---: |
| New occasional sprain applicability answer | 0 | 1 |
| Rehab completion choice per session | 1 | 1 |
| Better / Same / Worse injury answer when needed | 1 | 1 |
| Existing next-day injury response when due | 1 | 1 |
| New daily questions | 0 | 0 |
| Assessment measurements/date/time entries | 0 | 0 |

The existing clearance choices are only updated when clinician advice changes.
For the RESTORE pair, one injury response addresses its owned drill exposures
behind the scenes; it does not introduce two athlete questions. Modified work is
recorded without claiming the prescribed dose; skipped work creates no exposure.

## Validation scope

Tests cover real RESTORE completion → ordinary injury/next-day responses → usable
LOAD; normal LOAD completion and daily allocation; wrong ownership/side/episode;
missing evidence/permission/content/equipment; subtype/severity and structural/
instability concerns; setbacks and incomplete history; frozen history; other
injuries; guided intake generation; DYNAMIC/RETURN closure; internal-marker
display and unchanged daily UI controls. The activation manifest pins all 63
other profile hashes and the original ankle baseline prescriptions/bundle.
Generated bank audits include the one new identity; historical planning/archive
checks subtract only its exact approved content and profile delta.

Run `pytest tests/test_ankle_load_activation.py`, the rehab/clinical-policy suites,
bank validators and audit checks; run web unit tests, typecheck, lint and build.
CI results are reported in the PR. Unrelated failing Main checks are reported
separately, without changing application behaviour in this PR.
