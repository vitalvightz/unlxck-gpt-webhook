INJURY_SYNONYM_MAP = {
    # Ligament - now with every joint instability phrase imaginable
    "sprain": [
        "pop", "popped", "pop sound", "rolling", "rolled", "twist", "twisted",
        "wobbly", "wobble", "unstable", "instability", "gave way", "gave out",
        "folded", "buckled", "collapse", "loose", "shifty", "slippy", "sliding",
        "tore ligament", "ligament pop", "ligament tear", "ligament gone",
        "joint separation", "joint shift", "knee went", "ankle went", "wrist went",
        "partial dislocation", "sublux", "subluxation", "dislocate", "dislocated",
        "out of socket", "popped out", "click out", "shift out", "unhinged",
        "grade 1", "grade 2", "grade 3", "hyperextend", "overstretched", "overextension",
        "stretched ligament", "torn ligament", "ruptured ligament", "blown ligament",
        "sprain", "sprained", "inversion", "eversion", "rolled over", "turned over"
    ],

    # Muscle/Tendon - every possible pull/tear description
    "strain": [
        "pull", "pulled", "tug", "tugged", "tear", "torn", "rip", "ripped",
        "cramp", "cramping", "charley horse", "dead leg", "seize", "seized",
        "lock", "locked", "knot", "knotted", "ball", "balled", "grab", "grabbed",
        "ping", "pinged", "twinge", "twinging", "sharp pain", "acute pain",
        "muscle tear", "muscle rupture", "muscle pop", "muscle snap", "muscle went",
        "tendon tear", "tendon pop", "tendon snap", "tendon rupture",
        "hamstring", "calf", "quad", "groin", "pec", "bicep", "tricep",
        "strain", "strained", "grade 1", "grade 2", "grade 3", "muscle failure",
        "tendon failure", "overstretched", "overworked", "worked too hard"
    ],

    # Tightness - every stiffness phrase
    "tightness": [
        "tight", "tightness", "stiff", "stiffness", "locked", "locking",
        "won't move", "restricted", "stuck", "glued", "frozen", "rusty",
        "needs cracking", "needs popping", "needs release", "needs stretching",
        "hard to move", "limited motion", "reduced range", "can't extend",
        "can't flex", "can't rotate", "can't reach", "can't stretch",
        "morning stiffness", "first move", "warming up", "slow to loosen",
        "like a rock", "like concrete", "like a board", "like a log",
        "needs massage", "needs foam roll", "needs lacrosse ball"
    ],

    # Bruise - every impact description
    "contusion": [
        "bruise", "bruised", "black", "blue", "black and blue", "purple",
        "discoloration", "discolored", "kicked", "knee", "kneed", "elbow",
        "elbowed", "dead leg", "corked", "cork", "impact", "swollen",
        "dent", "dented", "indent", "indentation", "mark", "marked",
        "hit", "hitted", "struck", "stricken", "banged", "banged up",
        "trauma", "traumatic", "blunt", "blunt force", "from strike",
        "from kick", "from knee", "from elbow", "from impact", "from hit"
    ],

    # Swelling - every fluid retention phrase
    "swelling": [
        "swell", "swollen", "swelling", "puffy", "puffiness", "inflamed",
        "inflammation", "balloon", "ballooned", "blown up", "bloated",
        "pumped", "pumped up", "full", "fullness", "round", "rounded",
        "hot", "heat", "warm", "warmth", "fluid", "fluid retention",
        "edema", "oedema", "can't see bone", "can't see definition",
        "looks fat", "looks bigger", "looks swollen", "looks puffy",
        "like a balloon", "like a melon", "like a sausage"
    ],

    # Tendon Overuse - every chronic tendon phrase
    "tendonitis": [
        "tendon", "tendon pain", "tendon ache", "tendon sore", "tendon hurt",
        "tendonitis", "tendinosis", "tendinopathy", "grinding", "grind",
        "gritty", "grittiness", "achy", "aching", "flare", "flare up",
        "burn", "burning", "overuse", "repetitive", "chronic", "constant",
        "tender", "tenderness", "angry", "irritated", "irritation",
        "acting up", "playing up", "misbehaving", "problem area",
        "always sore", "always hurts", "never goes away", "persistent",
        "recurring", "comes and goes", "use pain", "activity pain"
    ],

    # Pinching - every joint catching phrase
    "impingement": [
        "pinch", "pinching", "click", "clicking", "clunk", "clunking",
        "catch", "catching", "jam", "jamming", "block", "blocking",
        "stuck", "sticking", "won't lift", "won't raise", "won't rotate",
        "won't turn", "won't reach", "won't extend", "won't move",
        "painful arc", "painful range", "limited by pain", "stopped by pain",
        "shoulder catch", "hip catch", "elbow catch", "wrist catch",
        "ankle catch", "knee catch", "joint catch", "bone on bone",
        "rubbing", "grinding", "bone rub", "impinge", "impingement"
    ],

    # Joint Instability - every giving way phrase
    "instability": [
        "loose", "looseness", "slip", "slipping", "slide", "sliding",
        "dislocate", "dislocating", "sublux", "subluxation", "partial",
        "partial dislocation", "give way", "giving way", "gave way",
        "unreliable", "unstable", "instability", "scary", "fear",
        "apprehension", "nervous", "nervousness", "hesitant", "hesitation",
        "trust issues", "don't trust", "afraid to move", "scared to move",
        "feels wrong", "feels off", "feels loose", "feels unstable",
        "feels unreliable", "feels dangerous", "feels unsafe"
    ],

    # Stiff Joint - every limited motion phrase
    "stiffness": [
        "stiff", "stiffness", "frozen", "freezing", "rusty", "rusted",
        "stuck", "sticking", "won't move", "won't bend", "won't flex",
        "won't extend", "won't rotate", "won't turn", "won't twist",
        "limited", "limitation", "reduced", "reduction", "restricted",
        "restriction", "can't move", "can't bend", "can't flex",
        "can't extend", "can't rotate", "can't turn", "can't twist",
        "morning", "first thing", "after rest", "after sitting",
        "after sleeping", "needs cracking", "needs popping", "needs loosening",
        "needs warming", "needs working", "needs mobilization"
    ],

    # General Pain - every pain descriptor
    "pain": [
        "pain", "painful", "hurt", "hurting", "ache", "aching", "sore",
        "soring", "sharp", "sharper", "stabbing", "sting", "stinging",
        "throb", "throbbing", "pulse", "pulsing", "burn", "burning",
        "nag", "nagging", "constant", "persistent", "ongoing", "chronic",
        "acute", "radiating", "radiate", "shooting", "traveling", "moving",
        "deep", "superficial", "surface", "internal", "external", "localized",
        "diffuse", "spread", "spreading", "widespread", "focused", "focal",
        "point", "specific", "general", "all over", "everywhere", "nowhere"
    ],

    # Soreness - every recovery phrase
    "soreness": [
        "sore", "soreness", "doms", "delayed", "delayed onset", "muscle soreness",
        "muscle pain", "muscle ache", "muscle hurt", "muscle fatigue",
        "beat up", "beaten up", "worked", "worked out", "trained", "trained hard",
        "recovery", "recovering", "post workout", "post training", "post session",
        "after workout", "after training", "after session", "next day", "next morning",
        "48 hour", "48 hours", "two day", "two days", "good pain", "good hurt",
        "bad pain", "bad hurt", "too much", "overdid it", "pushed too hard",
        "went too hard", "over trained", "over worked", "over reached"
    ],

    # Hyperextension - every overstretched phrase
    "hyperextension": [
        "hyperextend", "hyperextended", "hyperextension", "overextend", "overextended",
        "overextension", "overstretch", "overstretched", "overstretching",
        "bent back", "bent backward", "bent backwards", "folded back", "folded backward",
        "folded backwards", "locked out", "locked back", "locked backward",
        "locked backwards", "too far", "went too far", "pushed too far",
        "extended too far", "straightened too far", "reversed", "reversal",
        "backwards", "backward", "wrong way", "opposite way", "other way",
        "knee hyperextend", "elbow hyperextend", "wrist hyperextend",
        "finger hyperextend", "toe hyperextend", "joint hyperextend"
    ],

    # Vague - every uncertain phrase
    "unspecified": [
        "weird", "weirdness", "off", "offness", "wrong", "wrongness",
        "not right", "not normal", "not usual", "not typical", "not regular",
        "funny", "funniness", "strange", "strangeness", "odd", "oddness",
        "can't explain", "can't describe", "can't put finger on", "don't know",
        "not sure", "unsure", "uncertain", "mystery", "mysterious",
        "unknown", "unidentified", "undiagnosed", "unexplained", "unclear",
        "vague", "vagueness", "ambiguous", "ambiguity", "confusing", "confused",
        "puzzling", "puzzled", "perplexing", "perplexed", "baffling", "baffled"
    ]
}
