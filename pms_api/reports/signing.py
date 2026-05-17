"""
Signed download tokens for report files.

A token binds together a job uuid + the owner's user id + a timestamp, signed
with TimestampSigner. The download endpoint verifies the signature, expiry,
and the uuid binding; a leaked URL alone can't be used past expiry and a
URL signed for one job can't be used to download a different file.
"""

from django.conf import settings
from django.core.signing import BadSignature
from django.core.signing import TimestampSigner

_SALT = "report-download"


def _signer() -> TimestampSigner:
    return TimestampSigner(salt=_SALT)


def make_download_token(job) -> str:
    """Issue a fresh token for `job`. Called on every poll, not stored."""
    payload = f"{job.uuid}:{job.created_by_id}"
    return _signer().sign(payload)


def verify_download_token(token: str, expected_uuid) -> int:
    """
    Verify a token. Returns the user id encoded in the token.
    Raises BadSignature / SignatureExpired on any failure.
    """
    raw = _signer().unsign(token, max_age=settings.REPORT_DOWNLOAD_TOKEN_MAX_AGE)
    try:
        uuid_str, user_id = raw.split(":", 1)
    except ValueError as e:
        msg = "Malformed token payload."
        raise BadSignature(msg) from e
    if uuid_str != str(expected_uuid):
        msg = "Token does not match this report job."
        raise BadSignature(msg)
    return int(user_id)
