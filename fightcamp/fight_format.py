from __future__ import annotations

from copy import deepcopy
from typing import Any

from .conditioning import render_conditioning_block
from .rounds_format import (
    canonicalize_rounds_format_sport,
    parse_rounds_minutes as _parse_rounds_minutes,
)


FIGHT_FORMAT_RULES: dict[str, dict[str, Any]] = {
    "boxing_amateur_3x3": {
        "phases": {
            "GPP": {
                "render": {
                    "dosage_template": "3-4 rounds of 3 min @ RPE 6-7, 60-75 sec easy recovery, cap 16-20 min. Keep aerobic support present but not bloated.",
                    "weekly_progression": "Add 1 short round or about 5% work weekly; keep density conservative, then trim about 15-20% before SPP.",
                    "time_short": "Keep 2 aerobic rounds plus 1 crisp alactic burst cluster.",
                    "fatigue_note": "If fatigue high: keep aerobic support easy, cut glycolytic density first, and stop burst work before speed fades.",
                },
                "systems": {
                    "aerobic": {
                        "timing_hint": "18-22 min continuous support",
                    },
                },
            },
            "SPP": {
                "render": {
                    "dosage_template": "4-5 rounds of 3 min @ RPE 7-8, 60 sec rest, cap 12-15 min of work. Bias sharp repeatability over long grind.",
                    "weekly_progression": "Hold round length at 3 min; add a round only if quality stays sharp, then deload about 20% in the final SPP week.",
                    "time_short": "Keep 2 x 3 min fight-pace rounds plus 4-6 alactic bursts.",
                    "fatigue_note": "If fatigue high: keep the 3 min structure, drop 1 round, and lengthen rest before adding more density.",
                },
                "systems": {
                    "aerobic": {
                        "timing_hint": "12-18 min easy aerobic support",
                    },
                    "glycolytic": {
                        "timing_hint": "4-5 x 3 min rounds",
                        "rest_hint": "60 sec between rounds",
                    },
                    "alactic": {
                        "timing_target": "6-8 x 6-8 sec fast punch bursts",
                        "rest_target": "75-90 sec full recovery between reps",
                        "load_target": "RPE 8-9, sharp and relaxed, stop before speed drops",
                    },
                },
            },
            "TAPER": {
                "render": {
                    "dosage_template": "Early taper only: 3-4 rounds of 2-3 min @ RPE 6-7, then reduce density 40-50% and keep just 4-6 alactic bursts of 6-8 sec with full rest.",
                    "weekly_progression": "Reduce density 40-50%; keep the work crisp, low-damage, and very light in the final 3-5 days.",
                    "time_short": "Keep 2 short fight-pace rounds or 4-6 alactic bursts, not both at full dose.",
                    "fatigue_note": "If fatigue high: skip extra density and keep only 4-6 low-impact bursts plus rhythm work.",
                },
                "systems": {
                    "glycolytic": {
                        "display_name": "Fight-Pace Rounds",
                        "timing_target": "3-4 x 2-3 min work",
                        "rest_target": "60-75 sec between rounds",
                        "load_target": "RPE 6-7 fight-pace, stay sharp and under control",
                    },
                    "alactic": {
                        "timing_hint": "4-6 x 6-8 sec sharp bursts",
                        "rest_hint": "45-60 sec or full walk-back recovery",
                    },
                },
            },
        },
    },
    "boxing_amateur_5x3": {
        "phases": {
            "GPP": {
                "render": {
                    "dosage_template": "4-5 rounds of 3-4 min @ RPE 6-7, 60 sec easy recovery, cap 20-24 min. Build enough support for repeated 3 min rounds.",
                    "weekly_progression": "Add 1 short round or about 5-10% work weekly; keep the aerobic layer growing before pushing density.",
                    "time_short": "Keep 3 aerobic rounds plus 1 short alactic burst cluster.",
                    "fatigue_note": "If fatigue high: trim one glycolytic exposure first and keep the aerobic work easy.",
                },
                "systems": {
                    "aerobic": {
                        "timing_hint": "22-28 min continuous support",
                    },
                },
            },
            "SPP": {
                "render": {
                    "dosage_template": "5-6 rounds of 3 min @ RPE 7-8, 60 sec rest, cap 15-18 min of work. Push repeatability more than 3 x 3 without turning it into a grind.",
                    "weekly_progression": "Add a round or tighten density only when quality holds; deload about 20% in the final SPP week.",
                    "time_short": "Keep 3 x 3 min fight-pace rounds plus 4-5 alactic bursts.",
                    "fatigue_note": "If fatigue high: hold the 3 min structure, trim 1 round, and keep rest honest.",
                },
                "systems": {
                    "aerobic": {
                        "timing_hint": "15-20 min easy aerobic support",
                    },
                    "glycolytic": {
                        "timing_hint": "5-6 x 3 min rounds",
                        "rest_hint": "60 sec between rounds",
                    },
                    "alactic": {
                        "timing_target": "5-6 x 6-8 sec fast punch bursts",
                        "rest_target": "75-90 sec full recovery between reps",
                        "load_target": "RPE 8-9, sharp bursts only, no extra fatigue",
                    },
                },
            },
            "TAPER": {
                "render": {
                    "dosage_template": "Early taper only: 4-5 rounds of 2-3 min @ RPE 6-7, then reduce density 35-45% and keep just 5-6 alactic bursts of 6-8 sec with full rest.",
                    "weekly_progression": "Reduce density 35-45%; keep repeatability topped up without carrying fatigue into fight week.",
                    "time_short": "Keep 2-3 short fight-pace rounds or 5-6 alactic bursts.",
                    "fatigue_note": "If fatigue high: keep the taper to rhythm work and a small burst dose only.",
                },
                "systems": {
                    "glycolytic": {
                        "display_name": "Fight-Pace Rounds",
                        "timing_target": "4-5 x 2-3 min work",
                        "rest_target": "60 sec between rounds",
                        "load_target": "RPE 6-7 fight-pace, smooth and repeatable",
                    },
                    "alactic": {
                        "timing_hint": "5-6 x 6-8 sec sharp bursts",
                        "rest_hint": "45-75 sec or full walk-back recovery",
                    },
                },
            },
        },
    },
    "boxing_pro_10x3": {
        "phases": {
            "GPP": {
                "render": {
                    "dosage_template": "4-6 rounds of 4-5 min @ RPE 6-7, 45-75 sec easy recovery, cap 24-32 min. Build a deeper aerobic floor without wasting density.",
                    "weekly_progression": "Add 1 round or about 5-10% work weekly; build support first, then add density carefully.",
                    "time_short": "Keep 3 aerobic rounds plus 1 small alactic burst cluster.",
                    "fatigue_note": "If fatigue high: keep the aerobic support, drop optional density, and do not chase extra burst work.",
                },
                "systems": {
                    "aerobic": {
                        "timing_hint": "25-35 min continuous support",
                    },
                },
            },
            "SPP": {
                "render": {
                    "dosage_template": "6-8 rounds of 3 min @ RPE 7-8, 45-60 sec rest, cap 18-24 min of work. Build sustained repeatability without redlining.",
                    "weekly_progression": "Grow round count or tighten density slowly; protect quality and deload about 20% in the final SPP week.",
                    "time_short": "Keep 3-4 x 3 min fight-pace rounds plus 4-5 alactic bursts.",
                    "fatigue_note": "If fatigue high: keep sustained repeatability work but trim 1-2 rounds before adding rest debt.",
                },
                "systems": {
                    "aerobic": {
                        "timing_hint": "18-24 min easy aerobic support",
                    },
                    "glycolytic": {
                        "timing_hint": "6-8 x 3 min rounds",
                        "rest_hint": "45-60 sec between rounds",
                    },
                    "alactic": {
                        "timing_target": "4-5 x 6-8 sec fast punch bursts",
                        "rest_target": "90-120 sec full recovery between reps",
                        "load_target": "RPE 8, crisp speed only, no extra alactic inflation",
                    },
                },
            },
            "TAPER": {
                "render": {
                    "dosage_template": "Early taper only: 3-4 rounds of 3 min @ RPE 6-7, then reduce density 45-60% and keep just 4-5 alactic bursts of 6-8 sec with full rest.",
                    "weekly_progression": "Reduce density 45-60%; keep the work crisp and let sustained repeatability come down on purpose.",
                    "time_short": "Keep 2 short 3 min rounds or 4-5 alactic bursts.",
                    "fatigue_note": "If fatigue high: keep only rhythm work, easy support, and a very small burst dose.",
                },
                "systems": {
                    "glycolytic": {
                        "display_name": "Fight-Pace Rounds",
                        "timing_target": "3-4 x 3 min work",
                        "rest_target": "60 sec between rounds",
                        "load_target": "RPE 6-7 fight-pace, relaxed and repeatable",
                    },
                    "alactic": {
                        "timing_hint": "4-5 x 6-8 sec sharp bursts",
                        "rest_hint": "60-75 sec or full walk-back recovery",
                    },
                },
            },
        },
    },
    "mma_pro_3x5": {
        "phases": {
            "GPP": {
                "render": {
                    "dosage_template": "4-5 rounds of 4-5 min @ RPE 6-7, 60-90 sec easy recovery, cap 22-28 min. Build the aerobic floor for repeated 5 min efforts.",
                    "weekly_progression": "Add 1 short round or about 5-10% work weekly; add support first, then tighten density carefully.",
                    "time_short": "Keep 2 aerobic rounds plus 1 short fight-pace exposure.",
                    "fatigue_note": "If fatigue high: keep aerobic support, trim optional burst work, and do not chase extra density.",
                },
            },
            "SPP": {
                "render": {
                    "dosage_template": "4-5 rounds of 5 min @ RPE 7-8, 60 sec rest, cap 20-25 min of work. Build sustained repeatability without turning the week into a grind.",
                    "weekly_progression": "Hold the 5 min structure and add a round only when quality holds; deload about 20% in the final SPP week.",
                    "time_short": "Keep 2-3 x 5 min fight-pace rounds plus 3-4 short alactic bursts.",
                    "fatigue_note": "If fatigue high: keep the 5 min structure, drop 1 round, and lengthen rest before adding more density.",
                },
                "systems": {
                    "aerobic": {
                        "timing_hint": "15-20 min easy aerobic support",
                    },
                    "glycolytic": {
                        "timing_hint": "4-5 x 5 min rounds",
                        "rest_hint": "60 sec between rounds",
                    },
                    "alactic": {
                        "timing_target": "3-4 x 6-8 sec explosive bursts",
                        "rest_target": "90-120 sec full recovery between reps",
                        "load_target": "RPE 8, crisp power only, no extra burst inflation",
                    },
                },
            },
            "TAPER": {
                "render": {
                    "dosage_template": "Early taper only: 2-3 rounds of 5 min @ RPE 6-7, then reduce density 45-60% and keep just 3-4 alactic bursts of 6-8 sec with full rest.",
                    "weekly_progression": "Reduce density 45-60%; keep the work crisp and let hard repeatability come down on purpose.",
                    "time_short": "Keep 1-2 short fight-pace rounds or 3-4 alactic bursts.",
                    "fatigue_note": "If fatigue high: keep only rhythm work, easy support, and a very small burst dose.",
                },
                "systems": {
                    "glycolytic": {
                        "display_name": "Fight-Pace Rounds",
                        "timing_target": "2-3 x 5 min work",
                        "rest_target": "60-90 sec between rounds",
                        "load_target": "RPE 6-7 fight-pace, smooth and repeatable",
                    },
                    "alactic": {
                        "timing_hint": "3-4 x 6-8 sec sharp bursts",
                        "rest_hint": "60-90 sec or full walk-back recovery",
                    },
                },
            },
        },
    },
    "mma_pro_5x5": {
        "phases": {
            "GPP": {
                "render": {
                    "dosage_template": "5-6 rounds of 4-6 min @ RPE 6-7, 60-90 sec easy recovery, cap 26-34 min. Build a deeper aerobic floor for championship-length work.",
                    "weekly_progression": "Add 1 short round or about 5-10% work weekly; build support before adding hard density.",
                    "time_short": "Keep 3 aerobic rounds plus 1 small fight-pace exposure.",
                    "fatigue_note": "If fatigue high: preserve the aerobic base, trim hard density, and skip unnecessary burst work.",
                },
            },
            "SPP": {
                "render": {
                    "dosage_template": "5-6 rounds of 5 min @ RPE 7-8, 45-60 sec rest, cap 25-30 min of work. Prioritize sustained repeatability and careful density management.",
                    "weekly_progression": "Grow round count or tighten density slowly; protect quality and deload about 20% in the final SPP week.",
                    "time_short": "Keep 3 x 5 min fight-pace rounds plus 3 short alactic bursts.",
                    "fatigue_note": "If fatigue high: trim 1-2 rounds before adding more rest debt or burst work.",
                },
                "systems": {
                    "aerobic": {
                        "timing_hint": "18-24 min easy aerobic support",
                    },
                    "glycolytic": {
                        "timing_hint": "5-6 x 5 min rounds",
                        "rest_hint": "45-60 sec between rounds",
                    },
                    "alactic": {
                        "timing_target": "3 x 6-8 sec explosive bursts",
                        "rest_target": "90-120 sec full recovery between reps",
                        "load_target": "RPE 8, sharp power only, no extra burst inflation",
                    },
                },
            },
            "TAPER": {
                "render": {
                    "dosage_template": "Early taper only: 3-4 rounds of 5 min @ RPE 6-7, then reduce density 50-60% and keep just 3 alactic bursts of 6-8 sec with full rest.",
                    "weekly_progression": "Reduce density 50-60%; keep the work crisp and let the long-format fatigue come down deliberately.",
                    "time_short": "Keep 1-2 short fight-pace rounds or 3 alactic bursts.",
                    "fatigue_note": "If fatigue high: keep only rhythm work, easy support, and a tiny burst dose.",
                },
                "systems": {
                    "glycolytic": {
                        "display_name": "Fight-Pace Rounds",
                        "timing_target": "3-4 x 5 min work",
                        "rest_target": "60 sec between rounds",
                        "load_target": "RPE 6-7 fight-pace, relaxed and repeatable",
                    },
                    "alactic": {
                        "timing_hint": "3 x 6-8 sec sharp bursts",
                        "rest_hint": "60-90 sec or full walk-back recovery",
                    },
                },
            },
        },
    },
    "muay_thai_amateur_5x2": {
        "phases": {
            "GPP": {
                "render": {
                    "dosage_template": "4-5 rounds of 2-3 min @ RPE 6-7, 45-60 sec easy recovery, cap 16-20 min. Build repeatability for repeated 2 min striking rounds.",
                    "weekly_progression": "Add 1 short round or about 5-10% work weekly; keep the aerobic layer growing before pushing density.",
                    "time_short": "Keep 2 aerobic rounds plus 1 short alactic burst cluster.",
                    "fatigue_note": "If fatigue high: keep the support work easy and trim glycolytic density first.",
                },
            },
            "SPP": {
                "render": {
                    "dosage_template": "5-6 rounds of 2 min @ RPE 7-8, 60 sec rest, cap 10-12 min of work. Push repeatability and clinch pace without bloating the week.",
                    "weekly_progression": "Add a round only when quality holds; deload about 20% in the final SPP week.",
                    "time_short": "Keep 3 x 2 min fight-pace rounds plus 4-5 alactic bursts.",
                    "fatigue_note": "If fatigue high: hold the 2 min structure, drop 1 round, and keep rest honest.",
                },
                "systems": {
                    "aerobic": {
                        "timing_hint": "12-16 min easy aerobic support",
                    },
                    "glycolytic": {
                        "timing_hint": "5-6 x 2 min rounds",
                        "rest_hint": "60 sec between rounds",
                    },
                    "alactic": {
                        "timing_target": "4-5 x 6-8 sec explosive bursts",
                        "rest_target": "75-90 sec full recovery between reps",
                        "load_target": "RPE 8-9, sharp bursts only, no extra fatigue",
                    },
                },
            },
            "TAPER": {
                "render": {
                    "dosage_template": "Early taper only: 3-4 rounds of 2 min @ RPE 6-7, then reduce density 35-45% and keep just 4-5 alactic bursts of 6-8 sec with full rest.",
                    "weekly_progression": "Reduce density 35-45%; keep the work crisp and rhythmic into fight week.",
                    "time_short": "Keep 2 short fight-pace rounds or 4-5 alactic bursts.",
                    "fatigue_note": "If fatigue high: keep only rhythm work and a small burst dose.",
                },
                "systems": {
                    "glycolytic": {
                        "display_name": "Fight-Pace Rounds",
                        "timing_target": "3-4 x 2 min work",
                        "rest_target": "60 sec between rounds",
                        "load_target": "RPE 6-7 fight-pace, smooth and repeatable",
                    },
                    "alactic": {
                        "timing_hint": "4-5 x 6-8 sec sharp bursts",
                        "rest_hint": "45-75 sec or full walk-back recovery",
                    },
                },
            },
        },
    },
    "muay_thai_pro_3x3": {
        "phases": {
            "GPP": {
                "render": {
                    "dosage_template": "4-5 rounds of 3-4 min @ RPE 6-7, 45-60 sec easy recovery, cap 18-24 min. Build enough support for repeated 3 min rounds.",
                    "weekly_progression": "Add 1 short round or about 5-10% work weekly; keep the aerobic layer present before pushing density.",
                    "time_short": "Keep 2 aerobic rounds plus 1 short alactic burst cluster.",
                    "fatigue_note": "If fatigue high: keep support work easy and trim glycolytic density first.",
                },
            },
            "SPP": {
                "render": {
                    "dosage_template": "4-5 rounds of 3 min @ RPE 7-8, 60 sec rest, cap 12-15 min of work. Bias clean repeatability and sustained striking pace.",
                    "weekly_progression": "Hold round length at 3 min and add a round only when quality stays sharp; deload about 20% in the final SPP week.",
                    "time_short": "Keep 2-3 x 3 min fight-pace rounds plus 4 alactic bursts.",
                    "fatigue_note": "If fatigue high: keep the 3 min structure, drop 1 round, and lengthen rest before adding more density.",
                },
                "systems": {
                    "aerobic": {
                        "timing_hint": "14-18 min easy aerobic support",
                    },
                    "glycolytic": {
                        "timing_hint": "4-5 x 3 min rounds",
                        "rest_hint": "60 sec between rounds",
                    },
                    "alactic": {
                        "timing_target": "4 x 6-8 sec explosive bursts",
                        "rest_target": "75-90 sec full recovery between reps",
                        "load_target": "RPE 8-9, sharp bursts only, no extra fatigue",
                    },
                },
            },
            "TAPER": {
                "render": {
                    "dosage_template": "Early taper only: 3-4 rounds of 2-3 min @ RPE 6-7, then reduce density 40-50% and keep just 4 alactic bursts of 6-8 sec with full rest.",
                    "weekly_progression": "Reduce density 40-50%; keep the work crisp and low-damage into fight week.",
                    "time_short": "Keep 2 short fight-pace rounds or 4 alactic bursts.",
                    "fatigue_note": "If fatigue high: keep only rhythm work and a small burst dose.",
                },
                "systems": {
                    "glycolytic": {
                        "display_name": "Fight-Pace Rounds",
                        "timing_target": "3-4 x 2-3 min work",
                        "rest_target": "60 sec between rounds",
                        "load_target": "RPE 6-7 fight-pace, smooth and repeatable",
                    },
                    "alactic": {
                        "timing_hint": "4 x 6-8 sec sharp bursts",
                        "rest_hint": "45-75 sec or full walk-back recovery",
                    },
                },
            },
        },
    },
    "kickboxing_amateur_3x2": {
        "phases": {
            "GPP": {
                "render": {
                    "dosage_template": "3-4 rounds of 2-3 min @ RPE 6-7, 45-60 sec easy recovery, cap 14-18 min. Keep support work present without overbuilding density.",
                    "weekly_progression": "Add 1 short round or about 5% work weekly; keep density conservative before SPP.",
                    "time_short": "Keep 2 aerobic rounds plus 1 crisp alactic burst cluster.",
                    "fatigue_note": "If fatigue high: keep support easy, trim glycolytic density first, and stop burst work before snap fades.",
                },
            },
            "SPP": {
                "render": {
                    "dosage_template": "4-5 rounds of 2 min @ RPE 7-8, 60 sec rest, cap 8-10 min of work. Bias sharp repeatability and cleaner pace control.",
                    "weekly_progression": "Hold round length at 2 min; add a round only if quality stays sharp, then deload about 20% in the final SPP week.",
                    "time_short": "Keep 2-3 x 2 min fight-pace rounds plus 4-6 alactic bursts.",
                    "fatigue_note": "If fatigue high: keep the 2 min structure, drop 1 round, and lengthen rest before adding more density.",
                },
                "systems": {
                    "aerobic": {
                        "timing_hint": "10-14 min easy aerobic support",
                    },
                    "glycolytic": {
                        "timing_hint": "4-5 x 2 min rounds",
                        "rest_hint": "60 sec between rounds",
                    },
                    "alactic": {
                        "timing_target": "4-6 x 6-8 sec fast bursts",
                        "rest_target": "75-90 sec full recovery between reps",
                        "load_target": "RPE 8-9, sharp and relaxed, stop before speed drops",
                    },
                },
            },
            "TAPER": {
                "render": {
                    "dosage_template": "Early taper only: 3-4 rounds of 90-120 sec @ RPE 6-7, then reduce density 35-45% and keep just 4-6 alactic bursts of 6-8 sec with full rest.",
                    "weekly_progression": "Reduce density 35-45%; keep the work crisp, low-damage, and very light in the final 3-5 days.",
                    "time_short": "Keep 2 short fight-pace rounds or 4-6 alactic bursts, not both at full dose.",
                    "fatigue_note": "If fatigue high: skip extra density and keep only 4-6 low-impact bursts plus rhythm work.",
                },
                "systems": {
                    "glycolytic": {
                        "display_name": "Fight-Pace Rounds",
                        "timing_target": "3-4 x 90-120 sec work",
                        "rest_target": "60-75 sec between rounds",
                        "load_target": "RPE 6-7 fight-pace, stay sharp and under control",
                    },
                    "alactic": {
                        "timing_hint": "4-6 x 6-8 sec sharp bursts",
                        "rest_hint": "45-60 sec or full walk-back recovery",
                    },
                },
            },
        },
    },
    "kickboxing_pro_3x3": {
        "phases": {
            "GPP": {
                "render": {
                    "dosage_template": "4-5 rounds of 3-4 min @ RPE 6-7, 45-60 sec easy recovery, cap 18-22 min. Build enough support for repeated 3 min rounds.",
                    "weekly_progression": "Add 1 short round or about 5-10% work weekly; keep support present before pushing density.",
                    "time_short": "Keep 2 aerobic rounds plus 1 short alactic burst cluster.",
                    "fatigue_note": "If fatigue high: keep support easy and trim glycolytic density first.",
                },
            },
            "SPP": {
                "render": {
                    "dosage_template": "4-5 rounds of 3 min @ RPE 7-8, 60 sec rest, cap 12-15 min of work. Bias clean repeatability and sustained pace without cluttering the week.",
                    "weekly_progression": "Hold round length at 3 min; add a round only if quality stays sharp, then deload about 20% in the final SPP week.",
                    "time_short": "Keep 2 x 3 min fight-pace rounds plus 4-5 alactic bursts.",
                    "fatigue_note": "If fatigue high: keep the 3 min structure, drop 1 round, and lengthen rest before adding more density.",
                },
                "systems": {
                    "aerobic": {
                        "timing_hint": "12-16 min easy aerobic support",
                    },
                    "glycolytic": {
                        "timing_hint": "4-5 x 3 min rounds",
                        "rest_hint": "60 sec between rounds",
                    },
                    "alactic": {
                        "timing_target": "4-5 x 6-8 sec fast bursts",
                        "rest_target": "75-90 sec full recovery between reps",
                        "load_target": "RPE 8-9, sharp and relaxed, stop before speed drops",
                    },
                },
            },
            "TAPER": {
                "render": {
                    "dosage_template": "Early taper only: 3-4 rounds of 2-3 min @ RPE 6-7, then reduce density 40-50% and keep just 4-5 alactic bursts of 6-8 sec with full rest.",
                    "weekly_progression": "Reduce density 40-50%; keep the work crisp, low-damage, and very light in the final 3-5 days.",
                    "time_short": "Keep 2 short fight-pace rounds or 4-5 alactic bursts.",
                    "fatigue_note": "If fatigue high: keep only rhythm work and a small burst dose.",
                },
                "systems": {
                    "glycolytic": {
                        "display_name": "Fight-Pace Rounds",
                        "timing_target": "3-4 x 2-3 min work",
                        "rest_target": "60 sec between rounds",
                        "load_target": "RPE 6-7 fight-pace, smooth and repeatable",
                    },
                    "alactic": {
                        "timing_hint": "4-5 x 6-8 sec sharp bursts",
                        "rest_hint": "45-75 sec or full walk-back recovery",
                    },
                },
            },
        },
    },
}


def parse_rounds_minutes(rounds_format: str | None) -> tuple[int | None, int | None]:
    return _parse_rounds_minutes(rounds_format)


def get_fight_format_key(
    sport: str | None,
    status: str | None,
    rounds: int | None,
    minutes: int | None,
) -> str | None:
    normalized_sport = canonicalize_rounds_format_sport(sport)

    normalized_status = str(status or "").strip().lower()
    if normalized_status == "professional":
        normalized_status = "pro"
    elif normalized_status not in {"amateur", "pro"}:
        return None

    if normalized_sport not in {"boxing", "mma", "muay_thai", "kickboxing"}:
        return None

    if not isinstance(rounds, int) or not isinstance(minutes, int):
        return None

    key = f"{normalized_sport}_{normalized_status}_{rounds}x{minutes}"
    return key if key in FIGHT_FORMAT_RULES else None


def _merge_prescription(base: str | None, target: str | None, *, label: str) -> str | None:
    normalized_target = str(target or "").strip()
    if not normalized_target:
        return base

    normalized_base = str(base or "").strip()
    if not normalized_base:
        return normalized_target

    if normalized_target.lower() in normalized_base.lower():
        return normalized_base
    return f"{normalized_base}; {label}: {normalized_target}"


def _apply_system_modifiers(drill: dict[str, Any], system_rules: dict[str, str]) -> dict[str, Any]:
    updated = dict(drill)
    generic_fallback = bool(updated.get("generic_fallback"))

    base_timing = updated.get("timing") or updated.get("duration")
    base_rest = updated.get("rest")
    base_load = updated.get("load") or updated.get("intensity")

    if generic_fallback:
        display_name = str(system_rules.get("display_name", "")).strip()
        if display_name:
            updated["display_name"] = display_name
        if system_rules.get("timing_target"):
            updated["timing"] = system_rules["timing_target"]
        if system_rules.get("rest_target"):
            updated["rest"] = system_rules["rest_target"]
        if system_rules.get("load_target"):
            updated["load"] = system_rules["load_target"]
        return updated

    updated["timing"] = _merge_prescription(
        base_timing,
        system_rules.get("timing_hint") or system_rules.get("timing_target"),
        label="format target",
    )
    updated["rest"] = _merge_prescription(
        base_rest,
        system_rules.get("rest_hint") or system_rules.get("rest_target"),
        label="format rest",
    )
    updated["load"] = _merge_prescription(
        base_load,
        system_rules.get("load_hint") or system_rules.get("load_target"),
        label="format load",
    )
    return updated


def apply_fight_format_modifiers(
    conditioning_blocks: dict[str, dict | None],
    *,
    sport: str | None,
    status: str | None,
    rounds_format: str | None,
) -> tuple[dict[str, dict | None], str | None]:
    rounds, minutes = parse_rounds_minutes(rounds_format)
    format_key = get_fight_format_key(sport, status, rounds, minutes)
    if not format_key:
        return conditioning_blocks, None

    rules = FIGHT_FORMAT_RULES[format_key]
    updated_blocks = deepcopy(conditioning_blocks)

    for phase, block in updated_blocks.items():
        if not block:
            continue

        phase_rules = rules.get("phases", {}).get(str(phase).upper())
        if not phase_rules:
            continue

        grouped_drills = block.get("grouped_drills") or {}
        for system, drills in grouped_drills.items():
            system_rules = phase_rules.get("systems", {}).get(system)
            if not system_rules:
                continue
            grouped_drills[system] = [
                _apply_system_modifiers(drill, system_rules)
                for drill in drills
            ]

        block["format_key"] = format_key
        block["render_overrides"] = dict(phase_rules.get("render", {}))
        block["block"] = render_conditioning_block(
            grouped_drills,
            phase=phase,
            phase_color=block.get("phase_color", "#000"),
            missing_systems=block.get("missing_systems", []),
            num_sessions=block.get("num_sessions", 1),
            diagnostic_context=block.get("diagnostic_context", {}),
            sport=block.get("sport"),
            render_overrides=block.get("render_overrides"),
        )

    return updated_blocks, format_key
