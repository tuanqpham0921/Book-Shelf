"""Tests for require_app_check: off when no project number is configured, and
when on, only a token signed by Firebase's key for this project gets through."""

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.api import dependencies
from app.api.dependencies import require_app_check
from config import settings

PROJECT_NUMBER = "123456"
ISSUER = f"https://firebaseappcheck.googleapis.com/{PROJECT_NUMBER}"
FIREBASE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(key=FIREBASE_KEY, audience=f"projects/{PROJECT_NUMBER}", expires_in=3600):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        # real App Check tokens name the project both by number and by id
        "aud": [audience, "projects/tuanqpham0921"],
        "sub": "1:123456:web:abc",
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def enforced():
    """App Check on, with the key set standing in for Firebase's JWKS."""
    signing_key = MagicMock(key=FIREBASE_KEY.public_key())
    with patch.object(
        settings.app, "FIREBASE_PROJECT_NUMBER", PROJECT_NUMBER
    ), patch.object(
        dependencies._app_check_keys,
        "get_signing_key_from_jwt",
        return_value=signing_key,
    ):
        yield


def test_unconfigured_lets_everything_through():
    with patch.object(settings.app, "FIREBASE_PROJECT_NUMBER", None):
        require_app_check(None)  # must not raise


def test_a_valid_token_passes(enforced):
    require_app_check(_token())  # must not raise


def test_a_missing_token_is_refused(enforced):
    with pytest.raises(HTTPException) as exc:
        require_app_check(None)
    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(_token(key=OTHER_KEY), id="signed-by-someone-else"),
        pytest.param(_token(audience="projects/999"), id="another-project"),
        pytest.param(_token(expires_in=-60), id="expired"),
        pytest.param("not-a-jwt", id="garbage"),
    ],
)
def test_a_bad_token_is_refused(enforced, token):
    with pytest.raises(HTTPException) as exc:
        require_app_check(token)
    assert exc.value.status_code == 401
