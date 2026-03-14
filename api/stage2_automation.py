from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from fightcamp.stage2_pipeline import build_stage2_package, build_stage2_retry, review_stage2_output

_APP_STATUS_READY = "ready"
_APP_STATUS_REVIEW_REQUIRED = "review_required"
_STAGE2_PASS = "stage2_pass"
_STAGE2_RETRY_PASS = "stage2_retry_pass"
_STAGE2_FAILED = "stage2_failed"


class Stage2AutomationError(RuntimeError):
    """Raised when Stage 2 automation cannot complete successfully."""


class Stage2AutomationUnavailableError(Stage2AutomationError):
    """Raised when Stage 2 automation is not configured for runtime use."""


class Stage2Automator(Protocol):
    async def finalize(self, *, stage1_result: dict[str, Any]) -> dict[str, Any]: ...


def _strip_wrapping_code_fence(text: str) -> str:
    normalized = text.strip()
    if not normalized.startswith("```") or not normalized.endswith("```"):
        return normalized
    first_newline = normalized.find("\n")
    if first_newline == -1:
        return normalized.strip("`").strip()
    return normalized[first_newline + 1 : -3].strip()


def _extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return _strip_wrapping_code_fence(output_text)

    payload = response.model_dump(mode="python") if hasattr(response, "model_dump") else response
    if not isinstance(payload, dict):
        raise Stage2AutomationError("Stage 2 model returned an unreadable response payload.")

    parts: list[str] = []
    for item in payload.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = str(content.get("text") or "").strip()
                if text:
                    parts.append(text)

    combined = "\n".join(parts).strip()
    if not combined:
        raise Stage2AutomationError("Stage 2 model returned no plan text.")
    return _strip_wrapping_code_fence(combined)


def _base_result(stage1_result: dict[str, Any], *, draft_plan_text: str) -> dict[str, Any]:
    return {
        **stage1_result,
        "draft_plan_text": draft_plan_text,
        # The Stage 1 PDF reflects the raw draft, so do not publish it as the final athlete artifact.
        "pdf_url": None,
        "stage2_retry_text": "",
        "stage2_validator_report": {},
        "stage2_attempt_count": 0,
        "stage2_status": "",
        "final_plan_text": "",
    }


def _approved_result(
    stage1_result: dict[str, Any],
    *,
    draft_plan_text: str,
    final_plan_text: str,
    validator_report: dict[str, Any],
    attempt_count: int,
    stage2_status: str,
    retry_text: str = "",
) -> dict[str, Any]:
    return {
        **_base_result(stage1_result, draft_plan_text=draft_plan_text),
        "status": _APP_STATUS_READY,
        "plan_text": final_plan_text,
        "final_plan_text": final_plan_text,
        "stage2_status": stage2_status,
        "stage2_validator_report": validator_report,
        "stage2_retry_text": retry_text,
        "stage2_attempt_count": attempt_count,
    }


def _review_required_result(
    stage1_result: dict[str, Any],
    *,
    draft_plan_text: str,
    latest_plan_text: str,
    validator_report: dict[str, Any],
    retry_text: str,
) -> dict[str, Any]:
    return {
        **_base_result(stage1_result, draft_plan_text=draft_plan_text),
        "status": _APP_STATUS_REVIEW_REQUIRED,
        "plan_text": "",
        "final_plan_text": latest_plan_text,
        "stage2_status": _STAGE2_FAILED,
        "stage2_validator_report": validator_report,
        "stage2_retry_text": retry_text,
        "stage2_attempt_count": 2,
    }


@dataclass
class DisabledStage2Automator:
    reason: str

    async def finalize(self, *, stage1_result: dict[str, Any]) -> dict[str, Any]:
        raise Stage2AutomationUnavailableError(self.reason)


@dataclass
class OpenAIStage2Automator:
    client: Any
    model: str
    max_output_tokens: int | None = None

    @classmethod
    def from_env(cls) -> Stage2Automator:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return DisabledStage2Automator(
                "OPENAI_API_KEY is required for automated Stage 2 finalization."
            )

        try:
            from openai import AsyncOpenAI
        except ImportError:
            return DisabledStage2Automator(
                "The openai package is required for automated Stage 2 finalization."
            )

        model = os.getenv("UNLXCK_STAGE2_MODEL", "gpt-5-mini").strip() or "gpt-5-mini"
        timeout_seconds = float(os.getenv("UNLXCK_STAGE2_TIMEOUT_SECONDS", "90"))
        max_output_tokens = os.getenv("UNLXCK_STAGE2_MAX_OUTPUT_TOKENS", "").strip()
        client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=2)
        return cls(
            client=client,
            model=model,
            max_output_tokens=int(max_output_tokens) if max_output_tokens else None,
        )

    async def _generate_text(self, prompt: str) -> str:
        request: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
        }
        if self.max_output_tokens is not None:
            request["max_output_tokens"] = self.max_output_tokens
        try:
            response = await self.client.responses.create(**request)
        except Exception as exc:  # pragma: no cover - provider failure surfaces via integration
            raise Stage2AutomationError(f"Stage 2 model request failed: {exc}") from exc
        return _extract_response_text(response)

    async def finalize(self, *, stage1_result: dict[str, Any]) -> dict[str, Any]:
        package = build_stage2_package(stage1_result=stage1_result)
        draft_plan_text = str(package.get("draft_plan_text") or "")

        first_pass_text = await self._generate_text(str(package["handoff_text"]))
        first_review = review_stage2_output(
            planning_brief=package["planning_brief"],
            final_plan_text=first_pass_text,
        )

        if first_review["status"] == "PASS":
            return _approved_result(
                stage1_result,
                draft_plan_text=draft_plan_text,
                final_plan_text=first_pass_text,
                validator_report=first_review["validator_report"],
                attempt_count=1,
                stage2_status=_STAGE2_PASS,
            )

        retry = build_stage2_retry(
            stage1_result=stage1_result,
            final_plan_text=first_pass_text,
            validator_report=first_review["validator_report"],
        )
        retry_text = str(retry.get("repair_prompt") or "")
        if not retry_text:
            return _review_required_result(
                stage1_result,
                draft_plan_text=draft_plan_text,
                latest_plan_text=first_pass_text,
                validator_report=first_review["validator_report"],
                retry_text="",
            )

        second_pass_text = await self._generate_text(retry_text)
        second_review = review_stage2_output(
            planning_brief=package["planning_brief"],
            final_plan_text=second_pass_text,
        )
        if second_review["status"] == "PASS":
            return _approved_result(
                stage1_result,
                draft_plan_text=draft_plan_text,
                final_plan_text=second_pass_text,
                validator_report=second_review["validator_report"],
                attempt_count=2,
                stage2_status=_STAGE2_RETRY_PASS,
                retry_text=retry_text,
            )

        return _review_required_result(
            stage1_result,
            draft_plan_text=draft_plan_text,
            latest_plan_text=second_pass_text,
            validator_report=second_review["validator_report"],
            retry_text=retry_text,
        )


def build_default_stage2_automator() -> Stage2Automator:
    return OpenAIStage2Automator.from_env()
