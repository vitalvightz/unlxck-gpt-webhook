from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from storage3.exceptions import StorageApiError

from api.store import SupabaseAppStore


PRIVATE_PATH = "profile-private/feedback-private.png"
PROVIDER_MESSAGE = "provider leaked private object details"


def _store_with_failing_bucket(operation: str) -> SupabaseAppStore:
    client = MagicMock()
    bucket = client.storage.from_.return_value
    getattr(bucket, operation).side_effect = StorageApiError(
        PROVIDER_MESSAGE,
        "storage_error",
        500,
    )
    return SupabaseAppStore(client=client, admin_emails=set())


@pytest.mark.parametrize(
    ("operation", "invoke", "expected_detail"),
    [
        (
            "create_signed_url",
            lambda store: store.create_feedback_screenshot_signed_url(PRIVATE_PATH, expires_in=60),
            "failed to open feedback screenshot",
        ),
        (
            "upload",
            lambda store: store.upload_feedback_screenshot(PRIVATE_PATH, b"sanitised", "image/png"),
            "failed to upload screenshot",
        ),
        (
            "remove",
            lambda store: store.delete_feedback_screenshots([PRIVATE_PATH]),
            "failed to delete screenshot",
        ),
    ],
)
def test_feedback_storage_api_errors_use_sanitised_store_failure_path(
    operation,
    invoke,
    expected_detail,
    caplog,
):
    store = _store_with_failing_bucket(operation)

    with pytest.raises(HTTPException) as raised:
        invoke(store)

    assert raised.value.status_code == 500
    assert raised.value.detail == expected_detail
    assert "error_code=feedback_store_failure" in caplog.text
    assert "error_class=StorageApiError" in caplog.text
    assert PRIVATE_PATH not in caplog.text
    assert PROVIDER_MESSAGE not in caplog.text
