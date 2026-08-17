from uuid import UUID

import pytest
from fastapi import HTTPException

from app.auth import AuthVerifier


def test_authenticate_uses_verified_subject_as_user_id(monkeypatch):
    verifier = AuthVerifier("https://example.supabase.co", "authenticated")
    monkeypatch.setattr(
        verifier,
        "decode",
        lambda _token: {
            "sub": "11111111-1111-1111-1111-111111111111",
            "email": "reader@example.com",
            "user_metadata": {"display_name": "Reader"},
        },
    )

    user = verifier.authenticate("valid-token")

    assert user.id == UUID("11111111-1111-1111-1111-111111111111")
    assert user.email == "reader@example.com"
    assert user.display_name == "Reader"


@pytest.mark.parametrize("claims", [{}, {"sub": "not-a-uuid"}])
def test_authenticate_rejects_claims_without_valid_subject(monkeypatch, claims):
    verifier = AuthVerifier("https://example.supabase.co", "authenticated")
    monkeypatch.setattr(verifier, "decode", lambda _token: claims)

    with pytest.raises(HTTPException) as exc:
        verifier.authenticate("invalid-token")

    assert exc.value.status_code == 401


def test_authenticate_turns_jwt_errors_into_unauthorized(monkeypatch):
    verifier = AuthVerifier("https://example.supabase.co", "authenticated")

    def fail(_token):
        raise ValueError("bad signature")

    monkeypatch.setattr(verifier, "decode", fail)

    with pytest.raises(HTTPException) as exc:
        verifier.authenticate("invalid-token")

    assert exc.value.status_code == 401
