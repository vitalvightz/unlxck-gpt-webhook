"""One fixed sourced option; no verified-clinician pin or external load selection."""
from .lateral_elbow_progression import CRITERION, VERSION
from .reviewed_prescription import ReviewedPrescriptionOption, ReviewedDose, ReviewedCadence, ResistanceRule, ReviewTransition

SOURCES = ("https://www.jospt.org/doi/10.2519/jospt.2022.0302", "https://www.rjah.nhs.uk/our-services/therapy/supported-self-care/tennis-elbow/", "https://pmc.ncbi.nlm.nih.gov/articles/PMC8432114/")
RESTRICTIONS = (
    "hand_weight_only_no_added_resistance",
    "supported_forearm_comfortable_clinician_assessed_range",
    "no_forceful_grip_speed_forced_range_or_automatic_increase",
    "stop_for_worsening_during_or_delayed_symptoms",
    "follow_clinician_restrictions_no_training_or_contact_clearance",
)
ELBOW_LOAD_OPTION = ReviewedPrescriptionOption(
    option_id="lateral_elbow_hand_weight_wrist_extension_v1", option_version=1,
    profile_id="elbow_tendonitis", criterion_id=CRITERION, criterion_version=VERSION,
    transition=ReviewTransition(from_stage="restore", to_stage="load"),
    drill_id="elbow_tendonitis_supported_hand_weight_wrist_extension",
    bank_hash="56ba697662f47d146b43af38d56c4712d0e645d986b4a51b5a5ffc3ecbd711ef",
    instructions='Support the affected forearm palm-down on a table with the wrist free to move. With the hand empty, raise the wrist in the comfortable range assessed by your clinician, then slowly lower over five seconds. Keep the forearm supported. No dumbbell, band, forceful grip, forced end range, speed or automatic increase. Stop if symptoms worsen during or after the work.',
    range_choices=("comfortable_clinician_assessed",), resistance_rules=(ResistanceRule(mode="bodyweight"),),
    dose_choices=(ReviewedDose(sets=1, reps=10),),
    cadence_choices=(ReviewedCadence(frequency="daily", minimum_gap_days=1),),
    mandatory_restrictions=RESTRICTIONS, allowed_restrictions=RESTRICTIONS,
)
