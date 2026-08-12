"""Approved deterministic notification copy variants."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from api.services.notification_foundation import list_recent_notification_deliveries


@dataclass(frozen=True)
class NotificationTemplate:
    intent: str
    variant_id: str
    title_template: str
    body_template: str
    locale: str = "en-GB"
    template_version: int = 1
    active: bool = True
    selection_weight: int = 1
    minimum_timing_confidence: str = "low"


_CORE_VARIANTS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "morning_readiness": (
        ("mr-01", "CAMP CHECK. REPORT IN.", "Sleep, body, pain. Give me the read before we set today's work."),
        ("mr-02", "MORNING CHECK. YOUR READ.", "Tell me how you slept, how you feel and what hurts before we train."),
        ("mr-03", "SET TODAY'S CALL.", "Check in now. Your sleep, body and pain decide how we attack today."),
        ("mr-04", "CAMP STARTS WITH THE READ.", "Report sleep, body and pain. Then we set the work."),
    ),
    "missed_checkin": (
        ("mc-01", "CHECK-IN STILL OPEN.", "Give me the read so today's call matches the athlete who showed up."),
        ("mc-02", "REPORT IN BEFORE TRAINING.", "Sleep, body and pain are still missing. Check in before the work starts."),
        ("mc-03", "I STILL NEED YOUR READ.", "Open Today and check in before we lock the session call."),
        ("mc-04", "DON'T TRAIN BLIND.", "Check in now so today's load reflects how you actually feel."),
    ),
    "daily_camp_briefing": (
        ("db-01", "TODAY'S WORK IS LXCKED.", "{session}. Keep the rest of the day pointed at it."),
        ("db-02", "TODAY HAS A JOB.", "{session}. Know the target and keep the day clean around it."),
        ("db-03", "CAMP BRIEFING.", "{session}. That is the priority. Everything else supports it."),
        ("db-04", "TODAY'S CALL IS SET.", "{session}. Open Today when you are ready to see the full brief."),
    ),
    "session_preparation": (
        ("sp-01", "GET READY FOR THE WORK.", "Fuel, hydrate and get your head on {session}. Training is later."),
        ("sp-02", "PREP STARTS NOW.", "Eat, drink and clear the noise before {session}."),
        ("sp-03", "POINT THE DAY AT TRAINING.", "Fuel and hydrate. {session} is the next job."),
        ("sp-04", "BUILD INTO THE SESSION.", "Get fuel, fluids and focus in place for {session}."),
    ),
    "session_near": (
        ("sn-01", "30 MINUTES. SWITCH ON.", "Open today's call before you put the work in."),
        ("sn-02", "THE SESSION IS CLOSE.", "Get changed, get warm and open the final call."),
        ("sn-03", "TIME TO LOCK IN.", "Training is close. Open Today and take the session in clean."),
        ("sn-04", "NEXT JOB: TRAIN.", "Finish the prep and open the session before you start."),
    ),
    "session_ready": (
        ("sr-01", "SESSION READY.", "{session}. Open the call and put the work in."),
        ("sr-02", "TODAY'S WORK IS LIVE.", "{session}. Start clean and execute the call."),
        ("sr-03", "YOU'RE UP.", "Open {session} and get to work."),
        ("sr-04", "START THE SESSION.", "{session}. Follow the call and earn the day."),
    ),
    "post_session_log": (
        ("pl-01", "SESSION DONE? LOG IT.", "Give me effort and pain while the work is still fresh."),
        ("pl-02", "BANK THE SESSION.", "Log effort and pain now so tomorrow's call has the full picture."),
        ("pl-03", "CLOSE THE LOOP.", "Session finished? Add effort, pain and any changes while you remember."),
        ("pl-04", "LOG THE WORK.", "Tell me what the session cost before the detail fades."),
    ),
    "injury_recheck": (
        ("ir-01", "HOW'S {body_area} TODAY?", "Better, same or worse? Update it before we set the load."),
        ("ir-02", "UPDATE {body_area}.", "Give me the current read before training changes the picture."),
        ("ir-03", "BODY CHECK: {body_area}.", "Tell me what changed so today's call stays honest."),
        ("ir-04", "DON'T GUESS ON {body_area}.", "Update it now. Better, same or worse decides the next move."),
    ),
    "high_pain_followup": (
        ("hp-01", "HOW DID YOUR BODY SETTLE?", "Yesterday's pain was high. Check in before we decide today's load."),
        ("hp-02", "PAIN FOLLOW-UP.", "Give me the morning read before we set today's work."),
        ("hp-03", "REPORT HOW YOU SETTLED.", "High pain needs a fresh read before the next session call."),
        ("hp-04", "BODY FIRST. THEN THE WORK.", "Check in now so yesterday's pain shapes today's decision."),
    ),
    "recovery_nudge": (
        ("rn-01", "RECOVERY IS THE WORK TODAY.", "Move, eat, hydrate and get the system ready for the next session."),
        ("rn-02", "BANK THE RECOVERY DAY.", "Keep the body moving lightly and make the next hard day easier."),
        ("rn-03", "NO HERO WORK TODAY.", "Recover with intent. Food, fluids, movement and sleep all count."),
        ("rn-04", "RESET FOR THE NEXT ROUND.", "Use today to absorb the work and arrive ready for what is next."),
    ),
}

_SINGLE_VARIANTS: dict[str, tuple[str, str, str]] = {
    "session_modified": ("sm-01", "ADAPT. DON'T FORCE IT.", "Today's session still counts. I've changed how we attack it."),
    "session_stop": ("ss-01", "NO TRAINING TODAY.", "A safety flag changed the call. Open Today and follow it."),
    "plan_ready": ("pr-01", "YOUR CAMP IS LXCKED IN.", "Your final camp is live. Open it and see the full build."),
    "plan_updated": ("pu-01", "YOUR PLAN HAS CHANGED.", "A material camp update is live. Open the plan to see what moved."),
    "training_week_complete": ("tw-01", "WEEK COMPLETE.", "The work is banked. Review it before the next block starts."),
    "xp_level_up": ("xp-01", "LEVEL UP.", "Completed work moved you forward. Open Progress to see the new level."),
    "fight_countdown": ("fc-01", "FIGHT WEEK IS CLOSING IN.", "{countdown}. Keep every decision pointed at the fight."),
    "coach_message": ("cm-01", "{title}", "{body}"),
}

BUNDLED_TEMPLATES: tuple[NotificationTemplate, ...] = tuple(
    NotificationTemplate(intent, variant_id, title, body)
    for intent, variants in _CORE_VARIANTS.items()
    for variant_id, title, body in variants
) + tuple(
    NotificationTemplate(intent, variant[0], variant[1], variant[2])
    for intent, variant in _SINGLE_VARIANTS.items()
)


class _SafeFormat(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


def _templates_for_intent(store: Any, intent: str, locale: str) -> list[NotificationTemplate]:
    custom = getattr(store, "list_notification_templates", None)
    if callable(custom):
        rows = custom(intent, locale=locale) or []
    else:
        client = getattr(store, "client", None)
        if client is None:
            rows = []
        else:
            try:
                response = (
                    client.table("notification_templates")
                    .select("*")
                    .eq("intent", intent)
                    .eq("locale", locale)
                    .eq("active", True)
                    .order("variant_id")
                    .execute()
                )
                rows = getattr(response, "data", None) or []
            except Exception:  # noqa: BLE001 - bundled approved copy is the safe fallback
                rows = []
    parsed: list[NotificationTemplate] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        try:
            parsed.append(
                NotificationTemplate(
                    intent=str(row.get("intent") or ""),
                    variant_id=str(row.get("variant_id") or ""),
                    title_template=str(row.get("title_template") or ""),
                    body_template=str(row.get("body_template") or ""),
                    locale=str(row.get("locale") or "en-GB"),
                    template_version=int(row.get("template_version") or 1),
                    active=bool(row.get("active", True)),
                    selection_weight=int(row.get("selection_weight") or 1),
                    minimum_timing_confidence=str(
                        row.get("minimum_timing_confidence") or "low"
                    ),
                )
            )
        except TypeError:
            continue
    if parsed:
        return [template for template in parsed if template.active]
    return [
        template
        for template in BUNDLED_TEMPLATES
        if template.intent == intent and template.locale == locale and template.active
    ]


def select_notification_template(
    store: Any,
    *,
    profile_id: str,
    intent: str,
    dedupe_key: str,
    context: Mapping[str, Any] | None = None,
    locale: str = "en-GB",
) -> tuple[str, str, str, int]:
    templates = _templates_for_intent(store, intent, locale)
    confidence = str((context or {}).get("_timing_confidence") or "low")
    confidence_rank = {"low": 1, "medium": 2, "high": 3}
    templates = [
        template
        for template in templates
        if confidence_rank.get(confidence, 1)
        >= confidence_rank.get(template.minimum_timing_confidence, 1)
        and not (
            template.intent == "session_near"
            and template.variant_id == "sn-01"
            and confidence != "high"
        )
    ]
    if not templates:
        raise ValueError(f"no approved notification template for intent={intent}")
    recent = list_recent_notification_deliveries(
        store,
        profile_id=profile_id,
        intent=intent,
        limit=max(2, len(templates)),
    )
    recent_ids = [str(row.get("variant_id") or "") for row in recent if row.get("variant_id")]
    blocked = set(recent_ids[: max(1, len(templates) - 1)])
    available = [template for template in templates if template.variant_id not in blocked]
    if not available:
        last_id = recent_ids[0] if recent_ids else ""
        available = [template for template in templates if template.variant_id != last_id] or templates
    weighted = [
        template
        for template in available
        for _ in range(max(1, int(template.selection_weight)))
    ]
    seed = f"{profile_id}:{intent}:{dedupe_key}:{max(t.template_version for t in templates)}"
    index = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % len(weighted)
    selected = weighted[index]
    values = _SafeFormat(
        {key: str(value or "").strip() for key, value in dict(context or {}).items()}
    )
    title = selected.title_template.format_map(values).strip()
    body = selected.body_template.format_map(values).strip()
    return title, body, selected.variant_id, selected.template_version


__all__ = [
    "BUNDLED_TEMPLATES",
    "NotificationTemplate",
    "select_notification_template",
]
