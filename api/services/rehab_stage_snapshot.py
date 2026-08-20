"""Resolve the current rehab stage at plan-generation time and hand it to the planner.

The problem this closes
-----------------------
Rehab stage answers *"what can this injured tissue tolerate today?"* and it moves
with the athlete's check-ins, not with the intake they filled in weeks ago. The
Today surface already resolves it live (``today_service._with_rehab_stage``). Plan
generation, however, used to run entirely off the stored intake — a different
clock — so a fighter whose ankle has settled to ``restore`` since intake could
still be handed ``calm`` drills, and one whose intake said ``restore`` could be
handed load work after a flare pulled the tissue back to ``calm``.

This module is the missing hop. At generation time it resolves the current stage
**server-side**, from the same authoritative history Today reads, through the same
pure resolver (:func:`api.contracts.rehab_stage.resolve_rehab_stages`), and stamps
it onto the planner payload as *ephemeral generation context*. It is deliberately
**never written back into intake**: intake is not the source of truth for stage, so
persisting a resolved stage there would create a second, drifting copy. The stamp
lives only on the in-memory payload handed to Stage 1 for this one generation.

Identity, kept per episode
--------------------------
Each open ``injury_flags`` row is a distinct injury episode — it carries its own
``id`` (injury id), ``episode_id`` (rotated whenever the injury is re-reported),
``body_area`` and ``side``. The stage, the identity and the exposure trail of one
episode are only ever attached together, so a group of intake injuries that share
a body region can never end up with one episode's stage beside another's evidence.
An intake injury is matched to its flag by the same normalized
``(body_area, description)`` identity ``intake_injury_sync`` keys a flag on.

Degrades to silence
-------------------
Every read is best-effort. A missing store method, a raised read, an intake injury
with no matching flag, or a wound-care/unresolvable stage all leave the payload
untouched — which reads downstream as "stage not resolved", exactly the behaviour
before this hop existed. It can never *block* a generation.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from api.contracts.rehab_stage import resolve_rehab_stages

from .intake_injury_sync import _normalized_description, _normalized_token
from .today_service import (
    _checked_recent_session_completions,
    _checked_recent_today_checkins,
    _guided_injury_has_content,
    _guided_intake_injury_candidate,
)

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = ("open", "monitoring")
_HISTORY_LIMIT = 14
_EXPOSURE_LIMIT = 200


def _identity_key(body_area: object, description: object) -> tuple[str, str]:
    return (_normalized_token(body_area), _normalized_description(description))


def _flag_side(flag: Mapping[str, Any]) -> str | None:
    for key in ("side", "laterality"):
        value = str(flag.get(key) or "").strip()
        if value:
            return value.lower()
    return None


def _flag_exposures(
    store: Any, *, athlete_id: str, injury_id: str, episode_id: str
) -> list[dict[str, Any]]:
    """This episode's bounded rehab-exposure evidence, or ``[]`` on any failure."""
    reader = getattr(store, "list_rehab_exposures", None)
    if not callable(reader) or not injury_id or not episode_id:
        return []
    try:
        window = reader(
            athlete_id,
            injury_id=injury_id,
            injury_episode_id=episode_id,
            limit=_EXPOSURE_LIMIT,
        )
    except Exception:
        logger.exception(
            "[generation] rehab_exposure_read_failed athlete_id=%s injury_id=%s",
            athlete_id,
            injury_id,
        )
        return []
    rows = getattr(window, "rows", None)
    return list(rows) if isinstance(rows, list) else []


def _open_flags(store: Any, athlete_id: str) -> list[dict[str, Any]]:
    lister = getattr(store, "list_injury_flags", None)
    if not callable(lister):
        return []
    try:
        return [
            dict(flag)
            for flag in (lister(athlete_id, statuses=_ACTIVE_STATUSES, limit=500) or [])
            if isinstance(flag, Mapping)
        ]
    except Exception:
        logger.exception(
            "[generation] injury_flag_read_failed athlete_id=%s", athlete_id
        )
        return []


def resolve_open_injury_rehab_context(
    store: Any, athlete_id: str
) -> dict[tuple[str, str], dict[str, Any]]:
    """Resolve current rehab context for every open injury, keyed by identity.

    Returns a mapping ``(normalized body_area, normalized description) ->
    context`` where each context is one injury episode's resolved stage plus the
    identity and exposures the fightcamp selector keys on. Only injuries whose
    stage actually resolves on the musculoskeletal ladder are included; wound-care
    and unresolved injuries are omitted so they keep their pre-stage behaviour.
    """
    flags = _open_flags(store, athlete_id)
    if not flags:
        return {}

    checkins, _ = _checked_recent_today_checkins(store, athlete_id, limit=_HISTORY_LIMIT)
    completions, _ = _checked_recent_session_completions(
        store, athlete_id, limit=_HISTORY_LIMIT
    )
    try:
        decisions = resolve_rehab_stages(
            flags,
            current_checkin=None,
            previous_checkins=checkins,
            session_completions=completions,
        )
    except Exception:
        logger.exception(
            "[generation] rehab_stage_resolution_failed athlete_id=%s", athlete_id
        )
        return {}

    context_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    for flag in flags:
        injury_id = str(flag.get("id") or "")
        decision = decisions.get(injury_id)
        if decision is None or not decision.stage:
            continue
        episode_id = str(flag.get("episode_id") or "")
        key = _identity_key(flag.get("body_area"), flag.get("description"))
        # A newer open flag for the same identity wins (list is created-desc), so
        # the first one seen for a key is the current episode.
        if key in context_by_identity:
            continue
        context_by_identity[key] = {
            "rehab_stage": decision.stage,
            "rehab_care_pathway": decision.care_pathway,
            "injury_id": injury_id or None,
            "episode_id": episode_id or None,
            "athlete_id": athlete_id,
            "side": _flag_side(flag),
            "rehab_exposures": _flag_exposures(
                store,
                athlete_id=athlete_id,
                injury_id=injury_id,
                episode_id=episode_id,
            ),
        }
    return context_by_identity


def _guided_identity(injury: Mapping[str, Any]) -> tuple[str, str] | None:
    # Bootstrap ``cleared`` off so a medically-cleared-but-active injury still
    # matches its flag; the flag exists precisely because it is not resolved.
    bootstrap = {**injury, "cleared": ""}
    candidate = _guided_intake_injury_candidate(bootstrap, plan_id="")
    if candidate is None:
        return None
    return _identity_key(candidate.get("body_area"), candidate.get("description"))


def annotate_payload_with_rehab_stage(
    payload: Mapping[str, Any], *, store: Any, athlete_id: str
) -> dict[str, Any]:
    """Return a copy of ``payload`` with live rehab context stamped on its injuries.

    The stamp is ephemeral generation context — it is added to the payload handed
    to Stage 1 and never persisted. On any failure or absent match the payload is
    returned effectively unchanged, so this can only *add* stage awareness, never
    remove or block a generation.
    """
    if not isinstance(payload, Mapping) or not athlete_id:
        return dict(payload) if isinstance(payload, Mapping) else payload

    result = dict(payload)
    try:
        context_by_identity = resolve_open_injury_rehab_context(store, athlete_id)
    except Exception:
        logger.exception(
            "[generation] rehab_stage_snapshot_failed athlete_id=%s", athlete_id
        )
        return result
    if not context_by_identity:
        return result

    annotated_any = False

    def _annotate(injury: Mapping[str, Any]) -> dict[str, Any]:
        nonlocal annotated_any
        injury_dict = dict(injury)
        identity = _guided_identity(injury)
        if identity is None:
            return injury_dict
        context = context_by_identity.get(identity)
        if context is None:
            # Fall back to body-area-only identity when the description differs
            # (a re-worded intake note) but the region is unambiguous.
            body_only = [
                ctx_key for ctx_key in context_by_identity if ctx_key[0] == identity[0]
            ]
            if len(body_only) == 1:
                context = context_by_identity[body_only[0]]
        if context is None:
            return injury_dict
        injury_dict["rehab_generation_context"] = dict(context)
        annotated_any = True
        return injury_dict

    guided_injuries = result.get("guided_injuries")
    if isinstance(guided_injuries, list):
        result["guided_injuries"] = [
            _annotate(injury) if isinstance(injury, Mapping) and _guided_injury_has_content(injury) else injury
            for injury in guided_injuries
        ]

    guided_injury = result.get("guided_injury")
    if isinstance(guided_injury, Mapping) and _guided_injury_has_content(guided_injury):
        result["guided_injury"] = _annotate(guided_injury)

    if annotated_any:
        logger.info(
            "[generation] rehab_stage_snapshot_applied athlete_id=%s resolved_injuries=%s",
            athlete_id,
            len(context_by_identity),
        )
    return result


__all__ = [
    "annotate_payload_with_rehab_stage",
    "resolve_open_injury_rehab_context",
]
