"""Fixed seated ankle starter; no clinical review pin or resistance escalation."""
from .ankle_restore_load import CRITERION
from .reviewed_prescription import ReviewedPrescriptionOption, ReviewedDose, ReviewedCadence, ResistanceRule, ReviewTransition

RESTRICTIONS = ("seated_bilateral_floor_level_no_added_resistance", "comfortable_range_within_clinician_restrictions", "no_standing_step_forced_range_or_automatic_increase", "stop_for_worsening_during_or_delayed_symptoms", "no_sport_or_contact_clearance")
ANKLE_LOAD_OPTION = ReviewedPrescriptionOption(
    option_id="ankle_seated_heel_raise_v1", option_version=1,
    profile_id="ankle_sprain", criterion_id=CRITERION, criterion_version=1,
    transition=ReviewTransition(from_stage="restore", to_stage="load"),
    drill_id="ankle_sprain_seated_bilateral_heel_raise", bank_hash="358d6b8544800e9a90abc940cce456e30ade19200d824bccd8b78f5653a42d34",
    instructions='Sit on a stable chair with both feet flat on the floor. Keeping the front of both feet on the floor, slowly raise both heels within a comfortable range and slowly lower them to the floor. Stay seated; no weights, band, pressure on the knees, step, forced range or automatic increase. Follow clinician restrictions. Stop if pain or symptoms worsen during or after the work.',
    range_choices=("comfortable_within_clinician_restrictions",), resistance_rules=(ResistanceRule(mode="bodyweight"),),
    dose_choices=(ReviewedDose(sets=1, reps=10),), cadence_choices=(ReviewedCadence(frequency="daily", minimum_gap_days=1),),
    mandatory_restrictions=RESTRICTIONS, allowed_restrictions=RESTRICTIONS,
)
