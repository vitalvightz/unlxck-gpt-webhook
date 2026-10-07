"""Byte-bound authority from the private, service-only capture event stream.

The manual operator confirms source/qualification operationally. This does not
query a regulator, grant clinician status to admins, or trust uploaded documents.
"""
from dataclasses import dataclass
from hashlib import sha256

from api.contracts.clinical_progression_review import ReviewSource
from fightcamp.rehab_clinical import content_hash

REVIEW_EVENT = "clinical_progression_review"
LIFECYCLE_EVENT = "clinical_progression_review_lifecycle"
CAPTURE_POLICY = "authenticated_admin_independent_confirmation_v1"


@dataclass(frozen=True)
class PersistedClinicalReviewTrust:
    review_hashes: frozenset[str] = frozenset()
    lifecycle_hashes: frozenset[str] = frozenset()

    @classmethod
    def from_server_history(cls, rows):
        """Only call with complete raw service-store rows, never request JSON."""
        reviews, lifecycle = set(), set()
        for row in rows:
            payload, capture = row.get("payload") or {}, row.get("clinical_capture") or {}
            if not isinstance(payload, dict) or not isinstance(capture, dict):
                continue
            provenance = payload.get("provenance") or {}
            if not isinstance(provenance, dict):
                continue
            recorder, verifier = provenance.get("recorder") or {}, provenance.get("verifier") or {}
            if not isinstance(recorder, dict) or not isinstance(verifier, dict):
                continue
            digest = content_hash(payload)
            if (capture.get("policy") != CAPTURE_POLICY or capture.get("envelope_hash") != digest
                    or capture.get("recorder_id") != recorder.get("actor_id")
                    or recorder != verifier or recorder.get("role") != "operational_recorder"
                    or recorder.get("actor_id") == row.get("athlete_id")
                    or provenance.get("source") != ReviewSource.INDEPENDENT_CONFIRMATION.value
                    or not provenance.get("confirmed_at") or not provenance.get("confirmation_reference")
                    or not provenance.get("statement_hash") or not capture.get("request_hash")):
                continue
            if row.get("event_type") == REVIEW_EVENT:
                author = payload.get("clinical_author") or {}
                if not isinstance(author, dict):
                    continue
                if (author.get("author_id") in {recorder.get("actor_id"), row.get("athlete_id")}
                        or not author.get("qualification_reference") or not capture.get("statement_reference")
                        or not isinstance(capture.get("statement_text"), str) or not capture["statement_text"].strip()
                        or provenance.get("statement_hash") != sha256(capture["statement_text"].encode("utf-8")).hexdigest()
                        or any(payload.get(k) != row.get(k) for k in ("athlete_id", "injury_id", "injury_episode_id"))
                        or payload.get("review_id") != row.get("id")):
                    continue
                reviews.add(digest)
            elif row.get("event_type") == LIFECYCLE_EVENT and payload.get("lifecycle_id") == row.get("id"):
                lifecycle.add(digest)
        return cls(frozenset(reviews), frozenset(lifecycle))

    def review_trusted(self, review, *, as_of):
        return review.recorded_at <= as_of and content_hash(review.model_dump(mode="json")) in self.review_hashes

    def lifecycle_trusted(self, change, *, as_of):
        return change.recorded_at <= as_of and content_hash(change.model_dump(mode="json")) in self.lifecycle_hashes
