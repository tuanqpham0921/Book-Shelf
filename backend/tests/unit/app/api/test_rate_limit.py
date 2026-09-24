"""Tests for limit_messages_per_ip: off outside production, and in production a
per-IP ceiling keyed on the address Cloud Run appended, not one the caller wrote."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import dependencies
from app.api.dependencies import limit_messages_per_ip
from config import AppConfig, settings


def _request(forwarded_for: str) -> MagicMock:
    request = MagicMock()
    request.headers = {"x-forwarded-for": forwarded_for}
    return request


@pytest.fixture
def production():
    with patch.object(settings.app, "ENVIRONMENT", "production"), patch.dict(
        dependencies._recent_messages, clear=True
    ):
        yield


def _send(request, times):
    for _ in range(times):
        limit_messages_per_ip(request)


def test_up_to_the_limit_passes(production):
    _send(_request("1.1.1.1"), AppConfig.MESSAGES_PER_IP)  # must not raise


def test_one_past_the_limit_is_refused(production):
    request = _request("1.1.1.1")
    _send(request, AppConfig.MESSAGES_PER_IP)

    with pytest.raises(HTTPException) as exc:
        limit_messages_per_ip(request)
    assert exc.value.status_code == 429


def test_each_ip_has_its_own_count(production):
    _send(_request("1.1.1.1"), AppConfig.MESSAGES_PER_IP)
    limit_messages_per_ip(_request("2.2.2.2"))  # must not raise


def test_a_spoofed_first_entry_does_not_reset_the_count(production):
    """The caller controls everything before the last entry."""
    _send(_request("1.1.1.1"), AppConfig.MESSAGES_PER_IP)

    with pytest.raises(HTTPException):
        limit_messages_per_ip(_request("9.9.9.9, 1.1.1.1"))


def test_old_messages_age_out(production):
    request = _request("1.1.1.1")
    with patch("app.api.dependencies.time.monotonic", return_value=0.0):
        _send(request, AppConfig.MESSAGES_PER_IP)
    later = AppConfig.MESSAGES_PER_IP_WINDOW + 1
    with patch("app.api.dependencies.time.monotonic", return_value=later):
        limit_messages_per_ip(request)  # must not raise


def test_outside_production_nothing_is_counted():
    with patch.dict(dependencies._recent_messages, clear=True):
        _send(_request("1.1.1.1"), AppConfig.MESSAGES_PER_IP + 5)
        assert dependencies._recent_messages == {}
