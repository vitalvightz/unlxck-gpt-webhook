"""Tests for resolve_rehab_label_policy — the server-side Rehab/Prehab decision.

The policy is driven by the athlete's live injury flags, NOT the intake
"medically cleared" answer, and it is *per body region*: rehab work keeps the
"Rehab" label only while the region it targets is actually injured. These lock
in the behaviours that matter:

  * a cleared hamstring reads "Prehab" even while an unrelated quad is open
    (the bug this replaces: one open flag pinned the whole plan to "Rehab");
  * a still-open injury keeps its own region on "Rehab";
  * an injury whose region cannot be resolved falls back to "rehab" for
    everything, because it cannot be region-matched.
"""
from tests.support import FakeStore

from api.rehab_labels import normalize_match_term, resolve_rehab_label_policy

ATHLETE = "athlete-1"


def _flag(store: FakeStore, *, body_area: str, description: str, status: str) -> None:
    store.create_injury_flag(
        ATHLETE,
        {"body_area": body_area, "description": description, "status": status},
    )


def _policy(store: FakeStore):
    return resolve_rehab_label_policy(store, athlete_id=ATHLETE)


def _matches(policy, block_text: str) -> set[str]:
    """Regions whose terms appear in ``block_text`` — mirrors the web matcher."""
    haystack = f" {normalize_match_term(block_text)} "
    return {
        region.region
        for region in policy.active_regions
        if any(f" {term} " in haystack for term in region.terms)
    }


def test_no_injury_flags_defaults_to_prehab() -> None:
    policy = _policy(FakeStore())
    assert policy.default_mode == "prehab"
    assert policy.active_regions == []


def test_resolved_injury_is_not_active() -> None:
    store = FakeStore()
    _flag(store, body_area="left hamstring", description="strain", status="resolved")
    policy = _policy(store)
    assert policy.default_mode == "prehab"
    assert policy.active_regions == []
    assert _matches(policy, "Isometric Hamstring Bridge Hold") == set()


def test_open_injury_keeps_its_own_region_on_rehab() -> None:
    store = FakeStore()
    _flag(store, body_area="left hamstring", description="strain", status="open")
    policy = _policy(store)
    assert [region.region for region in policy.active_regions] == ["hamstring"]
    assert _matches(policy, "Isometric Hamstring Bridge Hold") == {"hamstring"}


def test_monitoring_injury_counts_as_active() -> None:
    store = FakeStore()
    _flag(store, body_area="left knee", description="tendon pain", status="monitoring")
    policy = _policy(store)
    assert [region.region for region in policy.active_regions] == ["knee"]


def test_cleared_region_reads_prehab_while_another_region_is_open() -> None:
    # The regression this replaces: a cleared hamstring stayed on "Rehab" purely
    # because an unrelated quad was open. Each region now answers for itself.
    store = FakeStore()
    _flag(store, body_area="left hamstring", description="strain", status="resolved")
    _flag(store, body_area="left quad", description="tightness", status="open")
    policy = _policy(store)
    assert policy.default_mode == "prehab"
    assert [region.region for region in policy.active_regions] == ["quads"]
    assert _matches(policy, "Isometric Hamstring Bridge Hold") == set()
    assert _matches(policy, "Spanish Squat Isometric — quad focus") == {"quads"}


def test_bank_drill_names_cover_blocks_that_never_name_the_region() -> None:
    # "Copenhagen" says nothing about the groin, so synonyms alone would let live
    # groin rehab read as "Prehab". The rehab bank supplies the missing term.
    store = FakeStore()
    _flag(store, body_area="groin", description="strain", status="open")
    policy = _policy(store)
    groin = next(region for region in policy.active_regions if region.region == "groin")
    assert any("copenhagen" in term for term in groin.terms)


def test_unlocalizable_open_injury_falls_back_to_rehab() -> None:
    # Nothing in the flag resolves to a body region, so no block can be matched
    # against it. Everything stays "Rehab" rather than guessing "Prehab".
    store = FakeStore()
    _flag(store, body_area="", description="feels off after sparring", status="open")
    policy = _policy(store)
    assert policy.default_mode == "rehab"
    assert policy.active_regions == []


def test_unlocalizable_open_injury_does_not_hide_a_localized_one() -> None:
    store = FakeStore()
    _flag(store, body_area="", description="feels off after sparring", status="open")
    _flag(store, body_area="left quad", description="tightness", status="open")
    policy = _policy(store)
    assert policy.default_mode == "rehab"
    assert [region.region for region in policy.active_regions] == ["quads"]


def test_region_spellings_fold_to_one_entry() -> None:
    # "glute" and "glutes" are distinct canonical keys upstream; two flags that
    # name the same region must not produce two regions.
    store = FakeStore()
    _flag(store, body_area="glute", description="strain", status="open")
    _flag(store, body_area="buttocks", description="soreness", status="open")
    policy = _policy(store)
    assert [region.region for region in policy.active_regions] == ["glute"]


def test_store_without_injury_flags_support_defaults_to_rehab() -> None:
    class BareStore:
        pass

    policy = resolve_rehab_label_policy(BareStore(), athlete_id=ATHLETE)
    assert policy.default_mode == "rehab"
    assert policy.active_regions == []


def test_store_failure_defaults_to_rehab() -> None:
    class BrokenStore:
        def list_injury_flags(self, *args, **kwargs):
            raise RuntimeError("supabase down")

    policy = resolve_rehab_label_policy(BrokenStore(), athlete_id=ATHLETE)
    assert policy.default_mode == "rehab"
    assert policy.active_regions == []
