"""The sport ban matches tag *words*, never raw substrings.

A tag names either a technique (``low_kick``) or an audience (``kickboxing``,
``kicker``). Matching blacklist terms as substrings of the joined tag string
could not tell the two apart, so ``"kick"`` inside ``"kickboxing"`` removed
every drill tagged for kickboxing athletes from a boxer's candidate pool -
including a wrist/finger rehab reset and a "Punch-Specific Max Isometric Hold".
Joining the tags also let a term match across the gap between two unrelated
adjacent tags: ``muay_thai clinch_knee`` contained the grappling phrase
``"thai clinch"``.

Name and notes remain substring matched; they are prose, not tokens.
"""
import pytest

from fightcamp.conditioning import is_banned_drill


# Real techniques a boxer cannot train must stay banned.
@pytest.mark.parametrize(
    "tag", ["low_kick", "body_kick", "switch_kick", "teep", "muay_thai"]
)
def test_technique_tags_stay_banned_for_boxing(tag):
    assert is_banned_drill("Heavy Bag Rounds", [tag], "boxing")


@pytest.mark.parametrize(
    "tag", ["wrestler", "grappler", "takedown", "sprawl", "bjj"]
)
def test_grappling_tags_stay_banned_for_striking_formats(tag):
    assert is_banned_drill("Circuit", [tag], "boxing")
    assert is_banned_drill("Circuit", [tag], "kickboxing")


# Audience tags describe who a drill serves, not what it contains.
@pytest.mark.parametrize("tag", ["kickboxing", "kicker"])
def test_audience_tags_do_not_ban_a_boxing_drill(tag):
    assert not is_banned_drill("Shadowboxing Intervals", [tag], "boxing")


def test_audience_tag_does_not_rescue_a_real_kick():
    # The technique tag still decides, whatever else the drill is tagged for.
    assert is_banned_drill("Pad Rounds", ["kickboxing", "low_kick"], "boxing")


def test_term_cannot_match_across_two_adjacent_tags():
    # The grappling phrase "thai clinch" spans the gap between these two
    # separate tags once joined, as it does on the real Counter Knee Matrix
    # record, banning a knee drill for a kickboxer as if it were grappling.
    assert not is_banned_drill(
        "Counter Knee Matrix", ["muay_thai", "clinch_knee"], "kickboxing"
    )


def test_prose_is_still_matched_as_substring():
    assert is_banned_drill("Takedown Entries", [], "boxing")
    assert is_banned_drill("Circuit", [], "boxing", "finish with a thai clinch hold")
