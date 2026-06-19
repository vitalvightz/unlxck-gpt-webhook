#!/usr/bin/env python3
"""Generate surface/skin-injury wound-care entries for ``data/rehab_bank.json``.

Surface injuries (cut, laceration, abrasion, graze, blister) are integumentary,
not musculoskeletal, so their "rehab" is wound care and graded return to
contact — never tissue-loading drills. This script appends a set of
clinically-appropriate wound-care protocols (keyed by surface type x body
location, covering all three camp phases) so the planner can prescribe real
management actions instead of falling through to generic loading drills.

Run once to (re)generate the surface block:

    python tools/generate_surface_rehab.py

It is idempotent: existing surface-type entries are dropped and rebuilt, all
non-surface entries are preserved in order.
"""

from __future__ import annotations

import json
from pathlib import Path

ARROW = "→"  # → matches the encoding used elsewhere in the bank
PHASES = f"GPP {ARROW} SPP {ARROW} TAPER"
SURFACE_TYPES = {"cut", "laceration", "abrasion", "graze", "blister"}

BANK_FILE = Path(__file__).resolve().parents[1] / "data" / "rehab_bank.json"


def _note(gpp: str, spp: str, taper: str) -> str:
    return f"GPP: {gpp} {ARROW} SPP: {spp} {ARROW} TAPER: {taper}"


# Reusable wound-care actions. Each is (name, GPP, SPP, TAPER) and deliberately
# avoids loading/severity-block terms (e.g. "heavy", "ballistic").
DRILLS: dict[str, dict] = {
    # Closed wounds (cut, laceration)
    "clean_close": {
        "name": "Clean & Approximate Edges",
        "notes": _note(
            "Irrigate the wound, then close with steri-strips or skin glue; get stitches if it is deep, gaping, or over a joint",
            "Re-support the edges with tape after each session so the wound does not gap open",
            "Confirm the wound is fully sealed and dry before competition week",
        ),
    },
    "waterproof_dressing": {
        "name": "Waterproof Occlusive Dressing",
        "notes": _note(
            "Cover with a waterproof dressing; change it daily and whenever it gets sweaty",
            "Re-dress before every session and protect the edges from sweat softening",
            "Switch to a light protective cover once the wound has closed",
        ),
    },
    "no_reopen": {
        "name": "No-Reopen Protection",
        "notes": _note(
            "Avoid stretching, friction, or contact directly over the wound",
            "Tape or pad the site before sparring and skip live contact if it can split open",
            "Avoid any contact that could reopen the wound before weigh-in and fight night",
        ),
    },
    "infection_check": {
        "name": "Daily Infection Check",
        "notes": _note(
            "Watch for spreading redness, warmth, swelling, pus, or fever and get it reviewed if any appear",
            "Check the site daily and pause training if infection signs develop",
            "Confirm the area is clean and closed before competition",
        ),
    },
    "scar_mobility": {
        "name": "Scar Mobility Once Closed",
        "notes": _note(
            "Leave the wound alone while it is still open",
            "Once fully closed, use gentle scar massage to keep the skin supple",
            "Keep the scar moisturised and mobile so it tolerates contact",
        ),
    },
    # Open superficial wounds (abrasion, graze)
    "debride_clean": {
        "name": "Debride & Clean Thoroughly",
        "notes": _note(
            "Rinse out all grit and debris with saline and clean the raw skin",
            "Re-clean after sweaty sessions to keep the surface free of contamination",
            "Keep the healing surface clean and intact",
        ),
    },
    "moist_dressing": {
        "name": "Moist-Healing Dressing",
        "notes": _note(
            "Cover with a non-stick dressing or hydrocolloid to keep it moist and protected",
            "Re-dress before training to cut down friction over the raw skin",
            "Use a minimal protective cover once new skin has formed",
        ),
    },
    "friction_offload": {
        "name": "Friction Offloading",
        "notes": _note(
            "Pad the area and keep mat, glove, or gi friction off the raw skin",
            "Tape or pad the site before grappling or bag work",
            "Protect the area from re-scraping in the final week",
        ),
    },
    "skin_barrier": {
        "name": "Skin Barrier Ointment",
        "notes": _note(
            "Apply an antiseptic barrier ointment to keep it moist and stop the scab cracking",
            "Reapply after showering and before bed",
            "Keep the skin supple so it does not crack under contact",
        ),
    },
    # Blisters
    "protect_blister": {
        "name": "Protect the Intact Blister",
        "notes": _note(
            "Do not pop an intact blister; cover it with a donut pad or hydrocolloid",
            "Pad the blister before sessions to take pressure off it",
            "Keep it protected and avoid any new friction",
        ),
    },
    "drain_blister": {
        "name": "Sterile Drainage If Tense",
        "notes": _note(
            "If it is large and painful, drain at the edge with a sterile needle, leave the roof on, and dress it",
            "Keep it clean and re-dressed and do not peel the roof off",
            "Make sure it is dry and closed before competition",
        ),
    },
    "fix_friction_source": {
        "name": "Fix the Friction Source",
        "notes": _note(
            "Find the cause — footwear, wraps, or grip — and change socks, wraps, or taping",
            "Pre-tape hot spots and use lubricant or powder to cut friction",
            "Lock in proven gear and add no new footwear or wraps on fight week",
        ),
    },
    "offload_substitute": {
        "name": "Offload & Substitute",
        "notes": _note(
            "Reduce volume on the irritated tissue while it settles",
            "Swap in low-friction conditioning so the blister can heal",
            "Keep only protected, pain-free work going into the fight",
        ),
    },
    "deroof_watch": {
        "name": "Deroof & Infection Watch",
        "notes": _note(
            "Watch for the roof tearing off, redness, or pus",
            "Pause friction work if the raw base is exposed",
            "Confirm it is healed or fully protected before fight night",
        ),
    },
    # Location-specific protections
    "facial_protection": {
        "name": "Facial Wound Protection",
        "notes": _note(
            "Butterfly-close the wound, keep it clean, and sleep on the opposite side",
            "Wear headgear and control sparring; avoid head contact that could split it",
            "Seal a well-healed cut and make sure there is no open wound at weigh-in",
        ),
    },
    "brow_care": {
        "name": "Brow & Orbital Cut Care",
        "notes": _note(
            "Close and dress the brow cut and avoid rubbing the eye area",
            "Protect the brow in sparring and avoid head clashes",
            "Confirm the brow is fully closed before competition",
        ),
    },
    "knuckle_wrap": {
        "name": "Knuckle Cut Wrapping",
        "notes": _note(
            "Clean and close the knuckle split and stay off the bag",
            "Add knuckle padding under wraps and avoid bag work until it closes",
            "Confirm it is sealed before gloving up",
        ),
    },
    "footwear_strategy": {
        "name": "Footwear & Sock Strategy",
        "notes": _note(
            "Switch to moisture-wicking socks and well-fitted mat shoes and tape known hot spots",
            "Pre-tape and powder the foot before sessions",
            "Use only proven, broken-in footwear in fight week",
        ),
    },
    "grip_strategy": {
        "name": "Grip Friction Strategy",
        "notes": _note(
            "Use chalk, grips, or tape and trim torn calluses flat",
            "Tape the palm hot spots and manage pulling volume",
            "Keep the grip protected and avoid new high-friction work",
        ),
    },
    "shin_sleeve": {
        "name": "Shin Sleeve Protection",
        "notes": _note(
            "Cover the mat burn with a non-stick dressing and a shin sleeve",
            "Wear a sleeve under the guard to stop re-scraping",
            "Protect the shin from re-abrasion before the fight",
        ),
    },
    "joint_pad": {
        "name": "Joint Pad Protection",
        "notes": _note(
            "Dress the mat burn and use a knee or elbow pad for grappling",
            "Keep the pad on for live rolls to protect the raw skin",
            "Protect the joint skin from friction pre-fight",
        ),
    },
}

# (type, location, [drill keys]). Location-specific drill first where relevant.
LAYOUT: list[tuple[str, str, list[str]]] = [
    # --- cut ---
    ("cut", "unspecified", ["clean_close", "no_reopen"]),
    ("cut", "face", ["facial_protection", "clean_close"]),
    ("cut", "jaw", ["facial_protection", "waterproof_dressing"]),
    ("cut", "eye", ["brow_care", "no_reopen"]),
    ("cut", "hand", ["knuckle_wrap", "infection_check"]),
    ("cut", "fingers", ["knuckle_wrap", "waterproof_dressing"]),
    ("cut", "forearm", ["waterproof_dressing", "no_reopen"]),
    ("cut", "elbow", ["no_reopen", "infection_check"]),
    ("cut", "knee", ["no_reopen", "scar_mobility"]),
    ("cut", "shin", ["waterproof_dressing", "infection_check"]),
    ("cut", "neck", ["clean_close", "no_reopen"]),
    ("cut", "foot", ["waterproof_dressing", "infection_check"]),
    # --- laceration ---
    ("laceration", "unspecified", ["clean_close", "infection_check"]),
    ("laceration", "face", ["facial_protection", "clean_close"]),
    ("laceration", "eye", ["brow_care", "clean_close"]),
    ("laceration", "jaw", ["facial_protection", "no_reopen"]),
    ("laceration", "hand", ["knuckle_wrap", "clean_close"]),
    ("laceration", "forearm", ["clean_close", "no_reopen"]),
    ("laceration", "elbow", ["no_reopen", "scar_mobility"]),
    ("laceration", "knee", ["no_reopen", "infection_check"]),
    ("laceration", "shin", ["clean_close", "waterproof_dressing"]),
    ("laceration", "neck", ["clean_close", "no_reopen"]),
    # --- abrasion ---
    ("abrasion", "unspecified", ["debride_clean", "moist_dressing"]),
    ("abrasion", "face", ["facial_protection", "debride_clean"]),
    ("abrasion", "neck", ["debride_clean", "friction_offload"]),
    ("abrasion", "shoulder", ["friction_offload", "moist_dressing"]),
    ("abrasion", "chest", ["friction_offload", "skin_barrier"]),
    ("abrasion", "elbow", ["joint_pad", "debride_clean"]),
    ("abrasion", "forearm", ["moist_dressing", "friction_offload"]),
    ("abrasion", "hip", ["friction_offload", "skin_barrier"]),
    ("abrasion", "knee", ["joint_pad", "moist_dressing"]),
    ("abrasion", "shin", ["shin_sleeve", "debride_clean"]),
    ("abrasion", "hand", ["friction_offload", "infection_check"]),
    ("abrasion", "upper_back", ["friction_offload", "moist_dressing"]),
    # --- graze ---
    ("graze", "unspecified", ["debride_clean", "skin_barrier"]),
    ("graze", "face", ["facial_protection", "skin_barrier"]),
    ("graze", "elbow", ["joint_pad", "skin_barrier"]),
    ("graze", "forearm", ["moist_dressing", "friction_offload"]),
    ("graze", "hand", ["friction_offload", "skin_barrier"]),
    ("graze", "hip", ["friction_offload", "moist_dressing"]),
    ("graze", "knee", ["joint_pad", "skin_barrier"]),
    ("graze", "shin", ["shin_sleeve", "skin_barrier"]),
    ("graze", "neck", ["debride_clean", "skin_barrier"]),
    ("graze", "foot", ["friction_offload", "skin_barrier"]),
    # --- blister ---
    ("blister", "unspecified", ["protect_blister", "fix_friction_source"]),
    ("blister", "foot", ["footwear_strategy", "protect_blister"]),
    ("blister", "heel", ["footwear_strategy", "drain_blister"]),
    ("blister", "toe", ["footwear_strategy", "offload_substitute"]),
    ("blister", "hand", ["grip_strategy", "protect_blister"]),
    ("blister", "fingers", ["grip_strategy", "deroof_watch"]),
    ("blister", "shin", ["shin_sleeve", "fix_friction_source"]),
    ("blister", "ankle", ["footwear_strategy", "protect_blister"]),
]


def build_surface_entries() -> list[dict]:
    entries: list[dict] = []
    for injury_type, location, drill_keys in LAYOUT:
        entries.append(
            {
                "location": location,
                "type": injury_type,
                "phase_progression": PHASES,
                "drills": [dict(DRILLS[key]) for key in drill_keys],
            }
        )
    return entries


def main() -> None:
    raw = BANK_FILE.read_text(encoding="utf-8")
    bank = json.loads(raw)
    if any(str(e.get("type") or "").lower() in SURFACE_TYPES for e in bank):
        raise SystemExit(
            "Surface entries already present; remove them before regenerating "
            "to keep the append idempotent."
        )

    surface = build_surface_entries()
    # Append surgically so existing (curated) entries keep their exact bytes;
    # only the new surface block is added before the closing bracket.
    closing = raw.rstrip()
    if not closing.endswith("]"):
        raise SystemExit("Unexpected rehab_bank.json structure (no closing ']').")
    body = closing[:-1].rstrip()  # drop trailing ']' and whitespace

    blocks = []
    for entry in surface:
        text = json.dumps(entry, indent=2, ensure_ascii=False)
        blocks.append("\n".join("  " + line for line in text.splitlines()))
    appended = body + ",\n" + ",\n".join(blocks) + "\n]\n"

    BANK_FILE.write_text(appended, encoding="utf-8")
    print(f"Appended {len(surface)} surface entries (bank total: {len(bank) + len(surface)}).")


if __name__ == "__main__":
    main()
