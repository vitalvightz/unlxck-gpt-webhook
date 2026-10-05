# Advanced rehab candidate review

Reviewed 2026-10-05 against Main `7f47255e6b4f3a975cec128f0af93424846e9256` after #2741.

**57 audit candidates before / 57 after; 54 remain in advanced planning, including 18 ready for clinical LOAD gate review. 23 profiles have exact-type inventory.** No production content, identity, review provenance, profile hash or stage is changed. All 64 profiles and 103 LIVE identities remain CALM/RESTORE only.

This is a clinically informed engineering shortlist, not independent clinical sign-off. A means mechanically suitable for the next clinical gate review, not safe to prescribe now. Ranking is a judgment about evidence applicability, current content, safety ambiguity and the size of the missing input work; it is not a candidate-count score.

## Recommended first wave

1. **achilles_tendonitis** — Direct tendon guidance and conservative anchor; first define site, function, symptoms and reviewed dose/gate.
2. **elbow_tendonitis** — Assessed lateral subtype only; supported lowering and grip/function assessment support a bounded next target.
3. **ankle_sprain** — Conditional lateral-ligament target; establish weight-bearing/ROM/control capture and useful prescription.
4. **shoulder_tendonitis** — Conditional cuff-compatible target after diagnosis/elevation/resistance assessment; one anchor still needs programme/dose review.
5. **groin_strain** — Conditional assessed acute-adductor target; supervised evidence is relevant but trusted assessment and entry criterion come first.

These are targets for scoped clinical/input work, not an activation batch. Start with Achilles and lateral-elbow subtype assessment. Ankle, shoulder and groin are conditional second steps. Tendon loading has the strongest direct guideline support here, but broad tendon labels cannot supply diagnosis or resistance selection; calf strain is not promoted just because tendon criteria exist.

## Dispositions and scope

| Code | Disposition | Count |
| --- | --- | ---: |
| A | READY_FOR_CLINICAL_GATE_REVIEW | 18 |
| B | REPAIR_BEFORE_GATE_REVIEW | 9 |
| C | INDICATION_UNCLEAR | 14 |
| D | DUPLICATE_OR_REDUNDANT_ADVANCED | 3 |
| E | DEFER_LOW_VALUE | 10 |
| F | DROP_AS_ADVANCED_CANDIDATE | 3 |

No candidate was repaired: the high-value instructions are already fixed. Unknown external resistance is an honest individual assessment gap, not a value to invent. Lower-priority misleading names, equipment constraints and restaging questions stay explicit follow-up work. F removes an item from this planning shortlist only; the rationalisation inventory still contains 57. D records functional overlap without merging/removing any near or uncertain duplicate. No candidate is deleted, restaged or newly approved.

Group GPP/SPP/TAPER labels survive as historical context; candidate instructions contain no affirmative camp-driven progression. The JSON records full current instructions, every mechanical field, review/source hashes and history, exact-type profile references and #2741 keeper links. Fixed mechanics does not imply a measured load, dose, disease-specific indication or adequate variety.

## Profile ranking

| Profile | Tier / priority | Exact reviewed | Fixed | Clean | Repair | LOAD shortlist | Variety / main reason |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| achilles_tendonitis | 1 / 1 | 1 | 1 | 1 | 0 | 1 | One clean floor-level anchor; limited variety. Strong direct tendon evidence and conservative fixed mechanics make the best next gate-review target; tendon-site assessment is still mandatory. |
| elbow_tendonitis | 1 / 2 | 1 | 1 | 1 | 0 | 1 | One clean supported extensor anchor; limited variety. Strong lateral-subtype guideline fit after confirmation; simple equipment and grip/function assessment support bounded next work. |
| ankle_sprain | 2 / 3 | 2 | 2 | 2 | 0 | 2 | Two controlled adjuncts, resisted motion and balance; incomplete graded strength variety. Principal additional prerequisite is assessed lateral-ligament injury with weight-bearing/ROM/control entry assessment; guidelines do not define this app gate. |
| shoulder_tendonitis | 2 / 4 | 1 | 1 | 1 | 0 | 1 | One fixed scaption anchor; incomplete programme variety. Principal prerequisite is rotator-cuff-compatible diagnosis and elevation/resistance assessment; generic tendon label cannot establish it. |
| groin_strain | 2 / 5 | 1 | 1 | 1 | 0 | 1 | One fixed adduction anchor; incomplete programme variety. Principal prerequisite is confirming acute adductor strain and assessed strength/stretch tolerance; supervised condition-specific evidence gives useful sport relevance. |
| calf_strain | 3 / 6 | 3 | 3 | 3 | 0 | 0 | Three foundation variants; no higher unilateral/graded resistance anchor. Calf-specific evidence supports strengthening, but these candidates add little to existing foundation and cannot establish unilateral capacity. |
| biceps_strain | 3 / 7 | 4 | 4 | 4 | 0 | 2 | One eccentric/one isometric anchor; overlap and equipment complexity. Tissue/site assessment, local strain transition evidence and strength/function inputs remain substantial gaps. |
| triceps_strain | 3 / 8 | 4 | 4 | 3 | 1 | 2 | Two local anchors plus compound/renaming debt. Strain site/integrity, overhead tolerance and local clinical gate evidence unresolved. |
| wrist_sprain | 3 / 9 | 6 | 6 | 3 | 3 | 2 | Six IDs overstate variety; three label/device defects and one overlap. Candidate count does not resolve ligament/site ownership, extension tolerance or a sourced gate. |
| shoulder_sprain | 3 / 10 | 4 | 4 | 4 | 0 | 2 | Two near-side anchors; overhead variants have weak ownership. Injured ligament and permitted positions are unspecified; generic shoulder-pain/instability criteria cannot substitute. |
| fingers_sprain | 3 / 11 | 4 | 4 | 3 | 0 | 1 | One controlled band anchor, one overlap and two questionable impact tasks. Digit/joint-specific stability/ROM and lesion assessment missing; taped quick taps lack generic advanced indication. |
| toe_sprain | 3 / 12 | 2 | 2 | 2 | 0 | 1 | One controlled forefoot anchor plus impact task. Joint/plantar-plate ownership needs assessment; pogo availability cannot make this a first LOAD target. |
| forearm_tendonitis | 3 / 13 | 1 | 1 | 1 | 0 | 0 | One extensor task with uncertain clinical ownership. Lateral-elbow evidence cannot establish generic forearm tendon diagnosis. |
| wrist_tendonitis | 3 / 14 | 1 | 1 | 1 | 0 | 0 | One flexor task with uncertain tendon ownership. Flexor-specific evidence absent; thumb-side tenosynovitis guidance cannot justify flexor loading. |
| shoulder_strain | 3 / 15 | 4 | 4 | 3 | 0 | 1 | One band anchor plus position ambiguity, complex load and early movement. Strain site/severity, local gate evidence and function cannot be inferred from rotator-cuff guidance. |
| quads_strain | 3 / 16 | 1 | 1 | 1 | 0 | 0 | One bodyweight hold; thin resistance/movement variety. Useful foundation but too thin with insufficient quad-specific gate evidence for first rollout. |
| hand_sprain | 3 / 17 | 4 | 4 | 4 | 0 | 1 | One simple grip anchor; finger tasks have weak hand-ligament ownership. Joint/ligament label too broad; grip completion cannot prove stability. |
| chest_strain | 4 / 18 | 2 | 2 | 2 | 0 | 0 | Early wall hold plus uncertain lengthened loading. Pectoral site/integrity and chest differential assessment unresolved; do not prioritise this set. |
| elbow_sprain | 4 / 19 | 2 | 2 | 1 | 0 | 0 | Uncertain overhead task plus early movement. Ligament scope and overhead safety have weak local gate evidence and little useful LOAD variety. |
| biceps_tendonitis | 4 / 20 | 1 | 1 | 1 | 0 | 0 | One curl with unclear proximal/distal ownership. Tendon-site ambiguity and limited applicable evidence do not justify a first-wave recommendation. |
| shoulder_instability | 4 / 21 | 4 | 4 | 2 | 2 | 0 | Two label defects and specialised carry variants. Instability direction/recurrence/apprehension need specialist assessment; cuff guidance cannot substitute. |
| knee_instability | 4 / 22 | 2 | 2 | 1 | 1 | 0 | Indirect hip/control task and misnamed foam task. Underlying pathology and knee-specific gate evidence missing; archive keeper content cannot change incidentally. |
| ankle_instability | 4 / 23 | 2 | 2 | 0 | 2 | 0 | Two impact tasks; zero controlled LOAD anchors. Current set is DYNAMIC only; selective LOAD needs different content and instability-specific assessment. |

Tier 1 = best next gate-review targets; Tier 2 = promising with one principal additional prerequisite beyond the shared capture/prescription work; Tier 3 = substantial evidence/input/content gaps; Tier 4 = do not pursue LOAD from this set yet. Fixed counts assess one bounded execution; clean counts additionally exclude B content defects and F advanced-stage mismatches. Unknown individual resistance is listed separately and never counted as known. A single useful anchor can justify investigating a profile, but none of the Tier 1/2 sets is a complete published LOAD programme.

## Captured data and shared blockers

**Already captured:** Athlete/injury/episode/side ownership, policy/bank provenance, completion state and amounts when explicitly quantified, categorical during/next-day response, stopped-work signals and injury status/history/setbacks. See rehab_completion.py, rehab_exposure.py, rehab_evidence.py and rehab_progression.py.

**Not currently captured:** No functional checkpoint is registered/read. No assessed subtype, observed ROM, strength, quality or regional clinical milestone enters the advanced evaluator. Numeric model fields do not demonstrate numeric symptom capture by the response flow.

**History can supply:** Exact-episode reviewed exposures, stated amounts, response groups and setbacks when complete/attributable; existing safety/data-sufficiency observations, not capacity measures.

**History cannot supply:** Diagnosis subtype, numeric pain from categorical response, ROM, grip strength, heel-rise quality, stability or unperformed-task tolerance. Counts cannot establish healing/clearance.

**Small product addition:** After clinical specification: timestamped injury/episode-specific assessment and function/symptom check-in recording assessor and actual result, plus real checkpoint reader/unknown handling. Design proposal, not new names or thresholds.

**Clinical boundary:** Every first-wave target needs reviewed exact-variant prescription/dose/indication, sourced entry criterion and setback policy. Clinician diagnosis/function assessment may be required; clearance flags are not quantitative readiness. No policy/schema/evaluator change here.

The model may store numeric symptoms or demand, but storage is not capture. Current answers are categorical and cannot become numeric pain, ROM, strength or movement-quality measurements. `CAPTURED_FUNCTIONAL_CHECKPOINTS` is empty and the evaluator has no implemented checkpoint reader. This review adds neither reader nor requirements. Zero transitions become technically evaluable or clinically promotable. LOAD/DYNAMIC/RETURN stay closed.

## Tier 1 / Tier 2 clinical and product review

### achilles_tendonitis — Tier 1

**Evidence and movement fit:** The Dutch guideline supports individual progressive calf strengthening and initially flat-surface insertional work. The 2024 CPG is midportion-specific. Floor-level lowering is plausible; neither establishes an app gate or eccentric superiority. [Dutch multidisciplinary guideline on Achilles tendinopathy](https://pmc.ncbi.nlm.nih.gov/articles/PMC8479731/), [Midportion Achilles tendinopathy revision 2024](https://www.orthopt.org/uploads/content_files/files/Achilles_Pain_revision_2024.pdf)

**Missing minimum inputs:** Assessed tendon site (midportion/insertional) and rupture/incompatible-pathology exclusion; actual loading-related pain rather than a categorical proxy; observed heel-rise function/quality and selected range/resistance tolerance. No universal entry cutoff asserted.

**Capture route:** Existing exact-episode history supplies work/amounts when reported, response groups and setbacks. Add clinician-scoped site/range/resistance assessment plus heel-rise function and numeric symptom check-in. Completion cannot derive capacity; define what requires clinician confirmation.

**Safety and transition:** Generic tendonitis does not identify site or rupture. Deep step lowering stays prohibited; preserve historical ID and conservative execution. Source-guided symptoms/fatigue and individual function require clinical translation into a bounded gate/dose. No time or repetition threshold imported.

### elbow_tendonitis — Tier 1

**Evidence and movement fit:** The CPG supports resisted wrist-extensor exercise for subacute/chronic lateral tendinopathy and ROM, grip and function measurement. Supported extensor lowering fits that subtype, not generic elbow tendonitis. [Lateral elbow pain and muscle function impairments 2022](https://www.orthopt.org/uploads/content_files/files/lucado_et_al_2022_lateral_elbow_pain_and_muscle_function_impairments.pdf)

**Missing minimum inputs:** Confirmed lateral extensor-origin condition and subacute/chronic applicability; elbow/wrist ROM, local irritability and measured/assessed grip/function; selected resistance/range and response. No grip-symmetry or pain threshold invented.

**Capture route:** Reuse categorical response/setback history only as support. Require site/clinical assessment and ROM/function check-in; grip strength needs appropriate measurement or clinician record, not soft-ball completion.

**Safety and transition:** Do not apply to medial/posterior pain or incompatible/neural pathology. Dumbbell demand correctly stays unknown until assessed. Phased loading is defensible but the CPG does not define this app ladder. Get a reviewed dose/gate and clinician-selected measurements; stay closed.

### ankle_sprain — Tier 2

**Evidence and movement fit:** The lateral-ankle CPG supports an individual structured programme including ROM, neuromuscular and balance work. Fixed motion/balance are plausible adjuncts, not universal foam-pad entry criteria. [Lateral ankle ligament sprains revision 2021](https://www.orthopt.org/uploads/content_files/files/jospt.2021.0302.pdf)

**Missing minimum inputs:** Assessed lateral ligament injury and stability/severity; actual weight-bearing pain/tolerance, dorsiflexion/ROM and observed stable-surface single-leg control; permitted direction/task tolerance before foam use.

**Capture route:** Completion cannot measure gait, ROM or control. Add weight-bearing/function check-in and clinician/physio ROM/control and injury-scope assessment; clinical thresholds need separate review.

**Safety and transition:** Syndesmotic injury, fracture concerns or persistent giving-way need assessment. Instability-profile hops remain separate DYNAMIC inventory. Severity/impairment-based exercise guidance gives no universal app cutoff. Clinician-reviewed ROM/control and symptom-tolerance criterion remains missing.

### shoulder_tendonitis — Tier 2

**Evidence and movement fit:** The 2025 cuff CPG supports active motor-control/resistance programmes and ROM, strength/function and load-tolerance assessment. Below-shoulder scaption is plausible after assessment, not proof of variant superiority or every tendon indication. [Rotator cuff tendinopathy diagnosis and rehabilitation 2025](https://doi.org/10.2519/jospt.2025.13182)

**Missing minimum inputs:** Clinician-assessed cuff-compatible diagnosis and incompatible-pathology exclusion; actual elevation ROM/function, irritability and assessed resistance tolerance; individual band and dose selection.

**Capture route:** Existing categorical observations cannot provide ROM/strength. Add regional function/symptom check-in and clinician diagnosis/resistance assessment; completion is not a surrogate.

**Safety and transition:** Scaption does not isolate one tendon. Cuff guidance cannot become instability clearance; unknown resistance stays unknown. Load tolerance is meaningful but no universal app threshold or higher-load superiority established. Clinically specify bounded entry criterion/dose; keep closed.

### groin_strain — Tier 2

**Evidence and movement fit:** A supervised acute-adductor cohort used progressive exercise and symptom-guided loading. Controlled adduction fits that indication; clinically pain-free/sport-training milestones are later rehab outcomes, not LOAD entry rules. [Criteria-based rehabilitation of acute adductor injuries in male athletes](https://journals.sagepub.com/doi/10.1177/2325967119897247)

**Missing minimum inputs:** Confirmed acute adductor injury versus other groin causes, assessed site/severity and compatible pathology; actual resisted-adduction symptoms, assessed adductor strength/function and stretch/range; documented resistance/dose.

**Capture route:** History cannot establish pain-free maximal strength or stretch tolerance. Require clinician/physio injury/adductor assessment then local symptom/task check-in; avoid unsupervised maximal diagnostic self-tests.

**Safety and transition:** Supervised male-athlete cohort cannot cover all groin causes/combat athletes. One light cable drill is not the full protocol. Clinically define initial loading eligibility; do not import sprinting, Copenhagen counts or sport-return milestones as LOAD criteria.

## Evidence inspection and limitations

- **achilles:** [Dutch multidisciplinary guideline on Achilles tendinopathy](https://pmc.ncbi.nlm.nih.gov/articles/PMC8479731/) — Multidisciplinary guideline, 2021; Diagnosis/treatment: individual progressive calf strengthening and flat-surface insertional advice. No universal app LOAD threshold or superior eccentric variant established.
- **achilles2024:** [Midportion Achilles tendinopathy revision 2024](https://www.orthopt.org/uploads/content_files/files/Achilles_Pain_revision_2024.pdf) — Clinical practice guideline; Scope and tendon-loading recommendations; directly retrieved and extracted PDF page 2 (CPG2). Midportion guidance cannot establish insertional or rupture eligibility.
- **ankle:** [Lateral ankle ligament sprains revision 2021](https://www.orthopt.org/uploads/content_files/files/jospt.2021.0302.pdf) — Clinical practice guideline; Structured therapeutic exercise recommendations and impairment/function assessment; directly retrieved and extracted PDF page 3 (CPG3). No automatic foam-pad/circumduction approval or app LOAD threshold.
- **calf:** [Assessment and management of calf muscle strain injuries](https://link.springer.com/article/10.1186/s40798-021-00364-0) — Qualitative study of 20 expert clinicians, 2022; Foundation function, single-leg quality and loaded strengthening. Expert practice, not a validated universal cutoff; do not borrow Achilles/return-to-running criteria.
- **elbow:** [Lateral elbow pain and muscle function impairments 2022](https://www.orthopt.org/uploads/content_files/files/lucado_et_al_2022_lateral_elbow_pain_and_muscle_function_impairments.pdf) — Clinical practice guideline; CPG2: resisted wrist extensors, ROM, pain-free/maximal grip and PRTEE/DASH; directly retrieved and extracted PDF page 2 (CPG2). Subacute/chronic lateral indication only; not arbitrary forearm, medial/posterior elbow or a universal stage cutoff.
- **groin:** [Criteria-based rehabilitation of acute adductor injuries in male athletes](https://journals.sagepub.com/doi/10.1177/2325967119897247) — Prospective supervised cohort, 2020, 81 male athletes; Exercise/symptom monitoring and clinically pain-free/controlled sport-training milestones. Acute-adductor cohort; sport-return milestones are not LOAD entry rules or evidence for all groin strains.
- **shoulder:** [Rotator cuff tendinopathy diagnosis and rehabilitation 2025](https://doi.org/10.2519/jospt.2025.13182) — Clinical practice guideline; Recommendations 1, 25 and 35-36: assessment, active exercise, load tolerance/function; directly retrieved APTA Rotator_Cuff_CPG.pdf page 3 (printed 237), alongside publisher extraction. No proof of high-load superiority, this scaption variant or all shoulder tendon/instability indications.

Sources justify movement families and assessment domains, not an app-defined RESTORE→LOAD threshold. Published return-to-sport milestones are not imported as LOAD entry rules. No new checkpoint names, numbers, dose or thresholds are prescribed here. Each selected profile still needs a reviewed exact-variant dose, defined symptom/setback policy and clinician-approved transition specification. Tier 3/4 is conservative deferral where the inspected evidence does not establish the exact ownership; it is not proof that exercise is ineffective.

## Every candidate decision

| ID | Profile | Stored → planning stage | Decision | Rationale / follow-up |
| --- | --- | --- | --- | --- |
| achilles_tendonitis_eccentric_calf_drops_on_step | achilles_tendonitis | load → load | A | Fixed floor-level lowering is a plausible exact-type anchor; establish tendon site and exclude incompatible pathology. The historical step ID remains; current mechanics prohibit step/deep lowering. |
| ankle_instability_foam_pad_jump_stick | ankle_instability | dynamic → dynamic | B | Jump landing belongs to DYNAMIC. Unknown impact and foam landing suitability require assessed demand/equipment review before a dynamic gate; no LOAD role. |
| ankle_instability_lateral_hop_stick_drill | ankle_instability | dynamic → dynamic | B | Fixed lateral hopping is DYNAMIC; impact/dose and instability-specific landing capacity remain unassessed, not LOAD merely because landing is controlled. |
| ankle_sprain_banded_ankle_circles | ankle_sprain | load → load | A | Fixed resisted circumduction is a plausible exact-type loading adjunct after lateral-ligament injury, permitted direction and symptom/ROM assessment; not evidence of healing. |
| ankle_sprain_single_leg_balance_on_foam_pad | ankle_sprain | load → load | A | Fixed supported single-leg balance is a plausible controlled weight-bearing adjunct. Assess stable-surface control first; it is not progressive resistance alone or sport clearance. |
| bicep_strain_band_resisted_eccentric_curl | biceps_strain | load → load | A | Supported assisted lift and fixed band lowering are plausible local strain loading; assess tissue/site independently of tendonitis criteria. |
| bicep_strain_cable_curl_with_fat_grip | biceps_strain | load → load | E | Fixed cable curling is usable, but thick grip adds equipment/complexity without established strain-specific advantage. Unknown resistance; prefer the simple band anchor. |
| bicep_strain_isometric_bicep_curl_hold_mid_range | biceps_strain | load → load | A | One supported mid-range self-resisted elbow-flexion hold is mechanically fixed and plausible strain loading; force and clinical gate remain unmeasured. |
| bicep_strain_supinated_isometric_elbow_hold | biceps_strain | load → load | D | Supported mid-flexion self-resisted hold materially overlaps the mid-range curl hold. Select one documented forearm-position variant for a small future set; preserve both inventory identities. |
| bicep_tendonitis_incline_db_curl_eccentric_focus | biceps_tendonitis | load → load | C | Current upright curl avoids historical incline stretch, but generic biceps tendonitis lacks proximal/distal tendon ownership. Unknown resistance and subtype indication block generic use. |
| calf_strain_active_band_calf_pumps | calf_strain | load → load | E | Fixed seated low-band plantarflexion is foundation work, insufficient alone for loaded calf capacity. Preserve the #2741 canonical keeper unchanged. |
| calf_strain_isometric_tip_toe_wall_press | calf_strain | load → load | E | Fixed bilateral heel-height hold is foundation loading, not unilateral capacity. Stronger graded/unilateral variety is missing; preserve archive keeper. |
| calf_strain_isometric_wall_push_hold | calf_strain | load → load | E | Fixed bilateral forefoot wall press provides foundation loading but does not establish unilateral calf capacity or useful graded resistance variety. Preserve archive keeper. |
| chest_strain_isometric_wall_push_chest_height | chest_strain | load → load | E | Gentle fixed wall press is plausible foundational pectoral loading but low added value; anatomical strain and regional transition evidence remain missing. |
| chest_strain_resistance_band_chest_fly | chest_strain | load → load | C | Fixed light fly is bounded, but unspecified pectoral site/severity makes lengthened loading ownership uncertain. Generic chest strain does not establish tissue integrity. |
| elbow_sprain_overhead_band_triceps_extension | elbow_sprain | load → load | C | Controlled extension is usable, but generic sprain lacks injured-ligament ownership and overhead-position suitability; needs exact injury assessment. |
| elbow_sprain_wrist_wall_slides_elbow_straight | elbow_sprain | load → restore | F | Current notes describe light comfortable supported movement without advanced resisted demand. Drop from advanced planning only; do not mutate stored stage or activate. |
| elbow_tendonitis_eccentric_reverse_wrist_curls | elbow_tendonitis | load → load | A | Supported extensor lowering fits assessed subacute/chronic lateral elbow tendinopathy, not medial/posterior tendon ownership. Unknown chosen dumbbell load is an individual prescription gap, not metadata to guess. |
| fingers_sprain_finger_band_expansions | fingers_sprain | load → load | A | Fixed low-band abduction is plausible controlled loading after injured-digit/joint assessment. It does not prove ligament stability or define a universal gate. |
| fingers_sprain_finger_taps_on_hard_surface | fingers_sprain | dynamic → restore | F | Slow light supported taps are movement/coordination, not demonstrated advanced impact loading. DYNAMIC/moderate-velocity metadata conflicts with current slow notes; omit from planning rather than approve/restage. |
| fingers_sprain_mini_band_finger_spread_hold | fingers_sprain | load → load | D | Low-band abduction hold materially overlaps finger expansions for a small first set, but contraction differs. Not an exact duplicate; retain both mechanics/identities. |
| fingers_sprain_tape_assisted_plyo_taps | fingers_sprain | dynamic → dynamic | C | Quick taped taps are DYNAMIC with unknown impact/load. Tape cannot establish injury-specific indication, joint stability or readiness. |
| forearm_tendonitis_eccentric_wrist_extensions | forearm_tendonitis | load → load | C | Fixed extensor lowering lacks specific tendon-site ownership. Lateral-elbow evidence cannot be assigned automatically to generic forearm tendonitis. |
| groin_strain_standing_cable_adduction | groin_strain | load → load | A | Fixed slow adduction is plausible for assessed acute adductor strain, not every groin cause. Establish injured tissue and symptom/function tolerance; define cable resistance/dose. |
| hand_sprain_band_resisted_finger_abduction | hand_sprain | load → load | C | Fixed finger abduction lacks relevance to an unspecified hand ligament. Region matching alone is insufficient; do not borrow finger-sprain criteria. |
| hand_sprain_finger_band_extensions | hand_sprain | load → load | C | Fixed finger opening is usable, but hand joint/ligament ownership is unspecified. No defensible generic hand-sprain gate follows from mechanics. |
| hand_sprain_hook_grip_plate_pinches | hand_sprain | load → load | E | Fixed plate grip adds equipment and unknown resistance without established first-wave advantage over supported soft-ball grip; joint/site still needs assessment. |
| hand_sprain_palm_squeeze_with_soft_ball | hand_sprain | load → load | A | Supported gentle soft-ball grip is a simple exact-type loading possibility conditional on joint/tissue assessment. Grip response does not prove ligament healing. |
| knee_instability_mini_band_lateral_walks | knee_instability | load → load | C | Fixed lateral steps may support hip/knee control but unspecified instability spans different pathology. Do not infer ACL clearance; preserve archive keeper/history. |
| knee_instability_reactive_knee_bounces_foam_pad | knee_instability | load → load | B | Notes describe slow bilateral supported bends, not reactive bounces. Misleading name and instability diagnosis need review. #2741 keeper cannot be silently edited; separate provenance-aware follow-up. |
| quads_strain_isometric_wall_sit_mid_range | quads_strain | load → load | E | Fixed partial-squat bodyweight hold is foundation loading. One hold lacks through-range/graded resistance variety and quad-specific gate evidence for first rollout. |
| shoulder_instability_banded_overhead_carries | shoulder_instability | load → load | C | Bounded overhead carry still lacks instability subtype/direction and permitted-range assessment. Unknown resistance/apprehension are not resolved by general shoulder-pain guidance. |
| shoulder_instability_kb_bottom_up_carry | shoulder_instability | load → load | E | Near-side fixed carry avoids overhead work but adds specialised grip/balance demand and unknown weight; lower priority than simple assessed shoulder loading. |
| shoulder_instability_quadruped_weight_shifts_arm_reaches | shoulder_instability | load → load | B | Current notes keep both hands down and prohibit reaches, unlike the name. Clarify descriptive label and wrist/shoulder demand and instability subtype before gate review. |
| shoulder_instability_wall_walks_isometric | shoulder_instability | load → load | B | Current notes specify a fixed wall hold and prohibit climbing, unlike the name. Needs descriptive label and instability-specific indication; rotator-cuff criteria cannot substitute. |
| shoulder_sprain_90_90_external_rotation_holds | shoulder_sprain | load → load | C | Fixed shoulder-height external-rotation hold may stress different injured structures. Generic sprain lacks ligament/site and tolerated-position assessment. |
| shoulder_sprain_isometric_banded_row | shoulder_sprain | load → load | A | Fixed arm-by-side row hold is a conservative controlled loading anchor after sprain site/stability assessment; mechanics do not supply clinical transition evidence. |
| shoulder_sprain_overhead_scapular_pull_aparts | shoulder_sprain | load → load | C | Bounded overhead band separation lacks established position/ligament relevance for generic shoulder sprain; indication needs exact assessment. |
| shoulder_sprain_wall_supported_external_rotation | shoulder_sprain | load → load | A | One gentle arm-by-side wall isometric is fixed exact-type inventory; joint/site and tolerated resistance still need clinical assessment. |
| shoulder_strain_banded_y_raise | shoulder_strain | load → load | A | Fixed comfortable low-band elevation is plausible after muscle-strain site assessment; completion/overhead comfort cannot establish readiness. |
| shoulder_strain_isometric_wall_press_90_abduction | shoulder_strain | load → load | C | Fixed shoulder-height isometric requires an assessed position/tissue. Generic strain does not specify which muscle or tear severity should be loaded. |
| shoulder_strain_landmine_shoulder_press | shoulder_strain | load → load | E | Controlled fixed landmine pressing is LOAD, but unknown weight, equipment and compound demand complicate first rollout; simpler local anchor has better value. |
| shoulder_strain_wall_slides_with_foam_roller | shoulder_strain | load → restore | F | No-band/no-weight comfortable wall slide is early movement/control without established advanced resistance demand. Drop from planning; retain identity/stored metadata pending separate review. |
| shoulder_tendonitis_banded_scaption_holds | shoulder_tendonitis | load → load | A | Fixed below-shoulder scaption is plausible for assessed rotator-cuff tendinopathy. It does not isolate a tendon; establish elevation/resistance tolerance and compatible diagnosis before gate review. |
| toe_sprain_double_leg_pogo_jumps | toe_sprain | dynamic → dynamic | C | Repeated impact pogos are DYNAMIC, never LOAD. Unknown impact and generic toe sprain do not establish plantar-plate/MTP versus other joint suitability. |
| toe_sprain_toe_off_isometric_presses | toe_sprain | load → load | A | Fixed gentle supported forefoot press is plausible if injured joint and permitted motion are assessed. One anchor is not a full LOAD set. |
| triceps_strain_isometric_wall_triceps_press | triceps_strain | load → load | A | Fixed gentle elbow-extension wall isometric is plausible exact-type strain loading; assess site, tissue integrity and function independently. |
| triceps_strain_kettlebell_crush_press_light | triceps_strain | load → load | E | Supported bilateral pressing is LOAD but adds chest/grip demand and unknown weight; lower value than simple local elbow loading for first rollout. |
| triceps_strain_overhead_band_triceps_extensions | triceps_strain | load → load | A | Fixed low-band elbow extension is plausible conditional on overhead comfort and injured tissue; no fatigue/speed escalation encoded. |
| triceps_strain_push_up_to_tabletop_flow | triceps_strain | load → load | B | Current task is one raised-table incline push-up and excludes reverse tabletop flow. Correct misleading descriptive name before gate review; do not restore the compound historical task. |
| wrist_sprain_band_assisted_wrist_flexion_hold | wrist_sprain | load → load | A | Fixed supported wrist-flexion hold is plausible after injured-joint/ligament assessment. Position tolerance does not prove stability or healing. |
| wrist_sprain_band_stabilization_circles | wrist_sprain | load → load | A | Fixed slow small resisted circumduction offers controlled variety conditional on exact injury and permitted direction/range; no escalation encoded. |
| wrist_sprain_isometric_wall_wrist_press | wrist_sprain | load → load | D | Gentle fixed wall hold overlaps supported neutral self-resisted hold in a small shortlist. Direction/support differ, so no identity consolidation or content deletion. |
| wrist_sprain_isometric_wrist_holds_various_angles | wrist_sprain | load → load | B | Current notes permit neutral only, unlike various-angles name. Clarify descriptive label/resistance direction in separate review; do not invent angular variants here. |
| wrist_sprain_plank_to_palm_rockbacks | wrist_sprain | load → load | B | Current task is knee-supported shifting, not full plank. Clarify descriptive label and permitted wrist-extension/loading after injury assessment; preserve fixed mechanics. |
| wrist_sprain_wrist_stability_drill_with_dynamometer | wrist_sprain | load → load | B | Notes describe grip loading and deny clearance inference. Stability name and fixed-resistance dynamometer wording confuse measurement with loading equipment; define assessed device/task before gate review. |
| wrist_tendonitis_eccentric_wrist_flexion_with_dumbbell | wrist_tendonitis | load → load | C | Supported flexor lowering does not fit every wrist tendonitis, especially thumb-side tenosynovitis. Current sources do not establish flexor-specific gate evidence; tendon/site and weight remain unresolved. |

LOAD means controlled resistance/loading; DYNAMIC means impact/reactive/faster work; RETURN means sport/contact integration. No candidate in this set supports RETURN-specific approval. Planning-stage differences above are recommendations, not bank mutations. Source names may describe retired execution variants; current notes and mechanics, not names, drive these decisions.

## Reproduction, changed files and validation

Production files are protected by the committed Main fingerprints in the curated decision source. The review tool consumes the freshly recomputed rationalisation audit and fails if candidate coverage or profile ownership drifts. The dedicated JSON and Markdown are deterministic. The three rationalisation documents were regenerated through their own audit tool and remain byte-identical because inventory is unchanged.

Changed files: `tools/rehab_advanced_candidate_decisions.json` (explicit review judgments and baseline), `tools/review_rehab_advanced_candidates.py` (read-only renderer), `docs/rehab-advanced-candidate-review.json`, this Markdown report, and `tests/test_rehab_advanced_candidate_review.py`.

Run `python tools/review_rehab_advanced_candidates.py --check`, `python tools/audit_rehab_bank_rationalisation.py --check`, and `python -m pytest tests/test_rehab_advanced_candidate_review.py tests/test_rehab_bank_rationalisation.py tests/test_rehab_exact_duplicate_cleanup.py tests/test_surface_wound_safety.py -q`. Existing bank/clinical/metadata/vocabulary validators and progression/Today/completion suites validate the protected production contracts. No database migration, deployment or frontend change is required.

### Validation results

- 667 passed: test_rehab_advanced_candidate_review.py, test_rehab_bank_rationalisation.py, test_rehab_exact_duplicate_cleanup.py, test_rehab_bank_schema.py, test_rehab_metadata_review_validation.py, test_surface_wound_safety.py and test_surface_injury_rehab.py (pytest -q).
- 485 passed: test_today_service.py, test_today_safety_matrix.py, test_multi_injury_today.py, test_clinician_clearance_today.py, test_rehab_completion_capture.py, test_api_rehab_completion_flow.py and test_rehab_prescription_bundles.py (pytest -q; 14 existing deprecation warnings).
- 717 passed: test_reviewed_rehab_progression.py, test_rehab_pathway_safety_invariants.py, test_rehab_pathway_equivalence.py and test_rehab_exposure_contract.py (pytest -q).
- Dedicated review module rerun after final report refinements: 148 passed. The three larger batches cover 1,869 cases; the dedicated rerun repeats cases in the first batch.
- Rehab bank validator: zero errors/warnings, 1,911 existing migration information items. Metadata review validator: valid. Clinical validator: 64 active profiles, zero promotable transitions.
- Injury vocabulary audit, tag authority gate, schema/tag migration --check, exact-duplicate consolidation --check and rationalisation --check passed.
- Ruff across api/fightcamp/tests/tools, review-module import, protected Main fingerprints, deterministic review --check and git diff checks passed. Regenerated rationalisation outputs match Main exactly.

No full-repository suite, production-history query or independent clinician sign-off was performed. Existing HTTP 422 deprecation warnings remain. The 1,149 general REPAIR entries, 22 near and 27 uncertain clusters remain untouched.
