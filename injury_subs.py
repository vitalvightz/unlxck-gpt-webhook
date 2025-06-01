injury_subs = {
    "feet": ["sledge pushes", "sled drags", "reverse lunges"],
    "ankle": ["step-ups", "glute bridges", "trap bar deadlift"],
    "shin": ["heel-elevated squats", "isometric wall sits", "sled drag"],
    "calf": ["box squats", "step-ups", "deadlifts with pause"],
    "knee": ["belt squat", "step-up (6'' box)", "reverse lunge"],
    "hamstring": ["glute bridge", "trap bar deadlift", "hip thrust"],
    "quad": ["hamstring curls", "step-ups", "RDL"],
    "hip flexors": ["glute bridge", "hip thrust", "single-leg RDL"],
    "glutes": ["quad extension", "heel-elevated goblet squat", "bike sprints"],
    "core": ["bird dog", "pallof press", "anti-rotation hold"],
    "lower back": ["trap bar deadlift", "leg press", "hip thrust"],
    "upper back": ["face pull", "band row", "push-ups"],
    "chest": ["landmine press", "DB fly", "cable press"],
    "obliques": ["anti-rotation press", "pallof hold", "deadbug"],
    "shoulders": ["landmine press", "neutral grip DB press", "banded overhead press"],
    "neck": ["band-resisted shrugs", "chin tucks", "isometric neck hold"],
    "hand": ["wrist wraps + barbell work", "machine press", "neutral grip options"],
    "wrist": ["neutral grip DB press", "trap bar press", "cable work"],
    "forearm": ["landmine press", "belt squat", "neutral grip pull"],
    "bicep": ["triceps focus", "hammer grip row", "pull-ups with straps"],
    "triceps": ["bicep work", "push-ups", "landmine press"]
}

import json
with open("/mnt/data/injury_subs.py", "w") as f:
    f.write("injury_subs = " + json.dumps(injury_subs, indent=4))
