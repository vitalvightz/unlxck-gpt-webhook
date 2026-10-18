"""Fixed wall-push-up starter; no clinical review pin or resistance escalation."""
from .shoulder_restore_load import CRITERION
from .reviewed_prescription import ReviewedPrescriptionOption, ReviewedDose, ReviewedCadence, ResistanceRule, ReviewTransition

RESTRICTIONS = ("wall_only_feet_near_wall_no_added_resistance", "comfortable_range_within_clinician_restrictions", "elbows_below_shoulders_no_foot_distance_or_automatic_increase", "stop_for_worsening_during_or_delayed_symptoms", "no_sport_or_contact_clearance")
SHOULDER_LOAD_OPTION = ReviewedPrescriptionOption(
    option_id="shoulder_wall_push_up_v1", option_version=1,
    profile_id="shoulder_tendonitis", criterion_id=CRITERION, criterion_version=1,
    transition=ReviewTransition(from_stage="restore", to_stage="load"),
    drill_id="shoulder_tendonitis_wall_push_up", bank_hash="49cb79339262cff700ea576553f2c8faafd7ba00d9f09b0da395e7c3f5d77fdc",
    instructions='Stand facing a stable wall, close enough to reach it comfortably without leaning. Place both hands on the wall at shoulder height, slightly wider than shoulder width, turned out slightly, with elbows below shoulders. Keep your body tall and feet fixed near the wall. Slowly bend your elbows a small comfortable amount to bring your body towards the wall, then gently push back. Keep within a pain-free range and clinician restrictions. Do not move your feet further back, lower your hands, add resistance or work to fatigue. Stop for pain, worsening symptoms during or after work, weakness or a feeling of instability.',
    range_choices=("comfortable_within_clinician_restrictions",), resistance_rules=(ResistanceRule(mode="bodyweight"),),
    dose_choices=(ReviewedDose(sets=1, reps=8),), cadence_choices=(ReviewedCadence(frequency="daily", minimum_gap_days=1),),
    mandatory_restrictions=RESTRICTIONS, allowed_restrictions=RESTRICTIONS,
)
