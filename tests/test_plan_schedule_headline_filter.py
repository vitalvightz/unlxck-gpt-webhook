from api.services.plan_schedule import has_scheduled_day_content


def _synthetic_entry(title: str) -> dict[str, str]:
    return {
        "status": "scheduled_session",
        "title": title,
        "coach_note": title,
        "effective_load": "reduced",
    }


def test_advisory_headlines_do_not_become_scheduled_sessions():
    for headline in (
        "Protect the body today",
        "Recovery is the priority",
        "Stay patient and refuel",
        "Protect freshness",
    ):
        assert has_scheduled_day_content(_synthetic_entry(headline)) is False, headline


def test_rest_prefix_vetoes_optional_work_language():
    for headline in (
        "Rest day — mobility optional",
        "No training today — breathing only",
        "Travel day — visualisation if useful",
    ):
        assert has_scheduled_day_content(_synthetic_entry(headline)) is False, headline


def test_explicit_support_headlines_remain_scheduled():
    for headline in (
        "Rhythm flush",
        "Breathing downshift",
        "Easy walk and visualisation",
        "Mindset reset",
        "Tactical watch",
    ):
        assert has_scheduled_day_content(_synthetic_entry(headline)) is True, headline


def test_combat_vocabulary_survives_inflection():
    """Inflected combat headlines are real work, not rest.

    The allowlist is a stem list wrapped in one trailing ``\\b``, so any stem
    without its own suffixes only matched the exact word. "spar" therefore never
    matched "Hard sparring" — the athlete's declared contact day — and Today,
    Overview and the completion write all treated that day as rest while Plan
    rendered it as a sparring session. These are the inflections the web
    client's ``classifySessionlessDay`` already recognises.
    """
    for headline in (
        "Hard sparring",
        "Sparring",
        "Light sparring",
        "Sparring and clinch",
        "Spars",
        "Sparred rounds",
        "Light combat",
        "Technical combat",
        "Shadowboxing",
        "Skills work",
        "Drills",
        "Coaching session",
    ):
        assert has_scheduled_day_content(_synthetic_entry(headline)) is True, headline


def test_rest_prefix_still_vetoes_combat_vocabulary():
    """A rest/off prefix outranks the combat words above."""
    for headline in (
        "Rest day — no sparring",
        "Off — skip the drills",
        "No training today — sparring cancelled",
    ):
        assert has_scheduled_day_content(_synthetic_entry(headline)) is False, headline


def test_real_structured_sessions_bypass_headline_only_gate():
    entry = {
        "status": "recovery",
        "title": "Recovery is the priority",
        "coach_note": "Keep the planned recovery session easy.",
        "effective_load": "reduced",
    }
    assert has_scheduled_day_content(entry) is True
