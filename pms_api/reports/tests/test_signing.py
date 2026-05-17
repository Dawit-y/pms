"""
Signed-download-token round-trip.
"""

import time
from types import SimpleNamespace

import pytest
from django.core.signing import BadSignature
from django.core.signing import SignatureExpired
from django.test import override_settings

from pms_api.reports.signing import make_download_token
from pms_api.reports.signing import verify_download_token


def _job(uuid: str = "11111111-1111-1111-1111-111111111111", user_id: int = 42):
    return SimpleNamespace(uuid=uuid, created_by_id=user_id)


def test_round_trip_returns_user_id():
    job = _job()
    token = make_download_token(job)
    uid = verify_download_token(token, job.uuid)
    assert uid == job.created_by_id


def test_tampered_token_raises():
    job = _job()
    token = make_download_token(job) + "x"
    with pytest.raises(BadSignature):
        verify_download_token(token, job.uuid)


def test_uuid_mismatch_raises():
    job = _job(uuid="11111111-1111-1111-1111-111111111111")
    token = make_download_token(job)
    with pytest.raises(BadSignature):
        verify_download_token(token, "22222222-2222-2222-2222-222222222222")


@override_settings(REPORT_DOWNLOAD_TOKEN_MAX_AGE=1)
def test_expired_token_raises():
    job = _job()
    token = make_download_token(job)
    time.sleep(2)
    with pytest.raises(SignatureExpired):
        verify_download_token(token, job.uuid)
