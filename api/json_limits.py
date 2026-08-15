"""Size and nesting guards for large JSON fields persisted to Supabase.

Athlete-supplied JSON (``onboarding_draft``, ``nutrition_profile``) and
server-assembled payloads (including ``request_payload`` and
``stage2_payload``) are stored verbatim in Supabase rows. Without bounds a
single request could store an
enormous or pathologically nested object, bloating the database and slowing the
app. These helpers enforce a byte-size ceiling and a maximum nesting depth.

Two enforcement layers use this module:

* Pydantic field validators at the request boundary (raise ``ValueError`` ->
  HTTP 422) for client-controlled fields.
* Store-side guards just before a Supabase write (raise the caller-supplied
  exception, typically ``HTTPException`` 413) as defense in depth.
"""

from __future__ import annotations

import json
from typing import Any, Callable

# Client-controlled free-form fields (onboarding_draft, nutrition_profile).
MAX_CLIENT_JSON_BYTES = 100 * 1024
# Server-assembled JSON fields use this limit unless a field-specific limit is
# explicitly defined below.
MAX_SERVER_JSON_BYTES = 256 * 1024
# Stage 2 includes legitimate, equipment-dependent candidate pools. Keep its
# persistence ceiling separate so other server and client JSON limits do not
# inherit the additional headroom.
MAX_STAGE2_PAYLOAD_BYTES = 384 * 1024
# Reject structures nested deeper than this regardless of byte size.
MAX_JSON_DEPTH = 32
# Coarse ceiling for the entire HTTP request body, enforced at the middleware
# layer via the declared Content-Length before the body is parsed or routed.
# Set comfortably above the largest legitimate server payload
# (``MAX_SERVER_JSON_BYTES``) so well-formed requests are never rejected, while
# still bounding pathological uploads.
MAX_REQUEST_BODY_BYTES = 1024 * 1024


def json_byte_size(value: Any) -> int:
    """Return the UTF-8 byte size of ``value`` serialized as compact JSON."""

    return len(json.dumps(value, default=str, separators=(",", ":")).encode("utf-8"))


def _max_depth(value: Any, *, limit: int) -> int:
    """Return the nesting depth of ``value``, short-circuiting once ``limit`` is
    exceeded.

    The walk is iterative so a deeply nested payload cannot exhaust the Python
    recursion limit before we get a chance to reject it. The returned value is
    capped at ``limit + 1`` (we only care whether it crossed the threshold).
    """

    deepest = 0
    # Stack of (node, depth) where depth is the node's own nesting level.
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > deepest:
            deepest = depth
        if depth > limit:
            # No need to descend further; we already know it's too deep.
            return deepest
        if isinstance(node, dict):
            for child in node.values():
                if isinstance(child, (dict, list, tuple)):
                    stack.append((child, depth + 1))
        elif isinstance(node, (list, tuple)):
            for child in node:
                if isinstance(child, (dict, list, tuple)):
                    stack.append((child, depth + 1))
    return deepest


def validate_json_field(
    value: Any,
    *,
    field: str,
    max_bytes: int = MAX_CLIENT_JSON_BYTES,
    max_depth: int = MAX_JSON_DEPTH,
    exc_factory: Callable[[str], Exception] = ValueError,
) -> Any:
    """Validate that ``value`` is within the size and depth limits.

    Returns ``value`` unchanged when valid (so it can be used inline in a
    Pydantic validator); raises ``exc_factory(message)`` otherwise. ``None`` and
    empty containers are always allowed.
    """

    if value is None:
        return value

    if _max_depth(value, limit=max_depth) > max_depth:
        raise exc_factory(f"{field} is nested too deeply (max {max_depth} levels)")

    size = json_byte_size(value)
    if size > max_bytes:
        raise exc_factory(
            f"{field} is too large ({size} bytes; max {max_bytes} bytes)"
        )

    return value
