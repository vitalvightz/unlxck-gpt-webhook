# Hamstring strain rehab policy (v1)

`hamstring_strain` is the third active policy, after the chest-strain and ankle-sprain pilots. It reviews two existing bank drills; no drill was added, renamed or split. Reviewed does not mean always prescribed: the scheduler, readiness, allocation, clinician-clearance and medical gates still decide what appears in Today. Activation is a software/data validation step, not clinician sign-off.

`tools/seed_rehab_hamstring_strain.py` reproduces the ledger reviews, the bank metadata and the policy hash. It refuses to run if a drill's source changed since review. It does not touch any other policy. `tools/seed_rehab_pilot.py` now keeps non-pilot policies when it rewrites the policy file.

## Evidence

| Source | Used for |
| --- | --- |
| [NHS: hamstring injury](https://www.nhs.uk/conditions/hamstring-injury/) | PRICE for the first 2 to 3 days. Avoid heat and massage for 3 days. Start gentle stretches once pain has started to settle, then walking, cycling and strengthening. Seek help for severe or worsening pain. |
| [Martin et al. 2022, JOSPT clinical practice guideline](https://www.jospt.org/doi/10.2519/jospt.2022.0301) | Stretching, stabilisation and strengthening early after injury, guided by pain tolerance. Strengthening 2 to 3 times per week. |
| [Heiderscheit et al. 2010, JOSPT](https://pubmed.ncbi.nlm.nih.gov/20118524/) | Phase 1 protects healing tissue, uses pain-free submaximal work, and progresses only on criteria. |
| [Erickson & Sherry 2017, J Sport Health Sci](https://pmc.ncbi.nlm.nih.gov/articles/PMC6189266/) | Pain-free submaximal isometric hamstring contractions in the first phase. |

The supervised protocols give set and hold numbers. They are not imported: every prescription remains self-paced (`dose: null`).

## Stage coverage

| Stage | Prescription | Gap |
| --- | --- | --- |
| CALM | `hamstring_unspecified_standing_bent_knee_stretch_active_rom`: slow, supported, pain-free bent-knee movement after the first 2 to 3 days. No bouncing, forcing or rotation. | 1 day (product cap, as for the ankle) |
| RESTORE | `hamstring_unspecified_standing_hamstring_isometric_against_wall`: a light, pain-free standing heel-press isometric, only once walking is comfortable. | 3 days, so at most 3 times per week (the CPG's 2–3 times per week) |

There is no stage bundle. The only complementary RESTORE candidate was the double-leg `hamstring_unspecified_isometric_hamstring_bridge_hold_30s`. Sherry & Best's ([JOSPT 2004](https://pubmed.ncbi.nlm.nih.gov/15089024/)) first phase does include a hook-lying bridge. But the drill is truthfully `bilateral_only`, and the existing completion contract cannot attribute bilateral work to a one-sided injury. In a bundle its completion would be silently dropped, losing its exposure and response evidence. Relabelling its laterality to get around that would be false metadata, so the bridge stays `needs_review`.

On a RESTORE recovery day, Today's existing lighter-alternative path offers the CALM movement instead. So movement can be daily and the isometric is spaced. Both drills are side-specific, so an episode without a recorded side receives no hamstring routine (fail closed).

LOAD, DYNAMIC and RETURN stay inactive. The engine disables them in v1, and the eccentric, Nordic, running and return-to-sport criteria they need have no reviewed bank content. Severe/high episodes, ruptures/tears and urgent tokens remain medical gates. The policy blocks hamstring-loading training at contact limit `none`. Clinician clearance can relax that block under the existing rules but never changes the stage.

## Bank audit (24 matching drills)

The matching groups are `hamstring/unspecified` (20 drills, compatible with the policy region) plus `hamstrings/strain` and `hamstrings/unspecified` (2 drills each). The `hamstrings` groups use an alias location, which the clinical bank validator rejects for the `hamstring` region. The `hamstrings` tightness, pain and soreness groups (6 drills) are other injury types and were not reviewed.

Reviewed: the 2 drills above. Their legacy notes describe later progressions (contralateral movement, rotation). These stay flagged `VARIABLE_DEMAND_PROGRESSION`, and the prescription instructions exclude them. Splitting the drills was not required.

Left `needs_review` (22):

| Drill(s) | Reason |
| --- | --- |
| `hamstring_unspecified_isometric_hamstring_bridge_hold_30s` | Clinically plausible, but `bilateral_only` completion cannot be attributed to a one-sided episode (see above). The "30s" label and single-leg-pulse progression are also unsourced. |
| `hamstrings_strain_isometric_hamstring_bridge`, `hamstrings_unspecified_single_leg_hamstring_bridge` | Alias-location duplicates of the bridge; the single-leg version is a higher-load progression. |
| `hamstrings_strain_massage_gun_biceps_femoris_sweep`, `hamstring_unspecified_foam_roller_hamstring_sweeps`, `hamstring_unspecified_self_massage_theracane_trigger_points` | Massage. NHS advises against it for the first 3 days; it is a passive modality, not staged exercise. |
| `hamstring_unspecified_heat_wrap_gentle_static_stretch` | Heat (NHS: avoid for 3 days) combined with a stretch: multi-demand. |
| `hamstring_unspecified_nordic_hamstring_curl_eccentrics`, `hamstring_unspecified_sliding_leg_curls_towel_on_floor`, `hamstring_unspecified_eccentric_slider_leg_curl_3s_lower`, `hamstrings_unspecified_slider_hamstring_curls`, `hamstring_unspecified_swiss_ball_hamstring_curls` | High-demand eccentric/lengthening work that needs progression criteria (LOAD). Some also need equipment. |
| `hamstring_unspecified_single_leg_romanian_deadlift_trx_assisted`, `hamstring_unspecified_kettlebell_swing_hinge_pattern_focus`, `hamstring_unspecified_lateral_lunge_with_hamstring_emphasis` | Loaded, ballistic or multiplanar deceleration work that belongs to later stages; already flagged for splitting where applicable. |
| `hamstring_unspecified_seated_band_resisted_knee_flexion`, `hamstring_unspecified_banded_good_morning_isometric_hold_at_45`, `hamstring_unspecified_mini_band_walks_monster_walks` | Band resistance unspecified and equipment-dependent; the progression changes the exposure. |
| `hamstring_unspecified_reverse_hyperextension_floor_version` | Progression adds ankle weights; loaded hip-extension demand is not set by the sources. |
| `hamstring_unspecified_supine_isometric_knee_extension_heel_dig` | The name (knee extension) contradicts the mechanism (heel dig = knee flexion). Correcting it would change the drill's identity. |
| `hamstring_unspecified_dynamic_pnf_stretching` | Vague contract-relax technique, possibly partner-assisted. |
| `hamstring_unspecified_aqua_jogging_high_knee_focus` | Needs a pool; conditioning rather than a staged tissue routine. |

## Persistence

No migration. The policy uses the existing schema, bundle allocation function and scheduling records. The bundle allocation migration already shipped with the engine.
