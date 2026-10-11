"""Service-only persistence; PostgreSQL rechecks actors and transitions atomically."""

from fastapi import HTTPException
from postgrest.exceptions import APIError


class CommunityStoreMixin:
    def community_rpc(self, name, params):
        if name not in {
            "community_command",
            "community_detail",
            "community_list",
            "community_owned_revision",
        }:
            raise ValueError("unsupported community operation")
        try:
            return self.client.rpc(name, params).execute().data
        except APIError as exc:
            code = str(exc.code)
            status = {"42501": 403, "P0002": 404, "40001": 409}.get(code, 422)
            message = {
                "42501": "This community action is not permitted.",
                "P0002": "Exercise not found.",
                "40001": "This exercise changed. Reopen it before continuing.",
            }.get(
                code,
                "Unable to complete this review step. Check the exercise, consent and video confirmation.",
            )
            if "quota" in str(exc):
                status, message = 429, "Contribution limit reached. Try again later."
            raise HTTPException(status, message) from None
