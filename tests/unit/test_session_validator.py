"""Unit tests for SessionValidator — pre-flight session/cookie validation."""

import importlib
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# Dynamic import because directory starts with digit
sv_mod = importlib.import_module("src.pipeline.4_submission.session_validator")
SessionValidationResult = sv_mod.SessionValidationResult
SessionValidator = sv_mod.SessionValidator


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_page(
    cookies=None,
    response_status=200,
    response_url="https://boards.greenhouse.io/techco/jobs/123",
    final_url=None,
):
    """Build a mock Playwright page with controllable cookies, response, and URL."""
    page = MagicMock()
    # page.context.cookies() returns list of cookie dicts
    ctx = MagicMock()
    ctx.cookies = AsyncMock(return_value=cookies or [])
    page.context = ctx

    # page.goto() returns a mock response
    resp = MagicMock()
    resp.status = response_status
    resp.url = response_url
    page.goto = AsyncMock(return_value=resp)

    # page.url — the URL after navigation (may differ from response.url if redirected)
    page.url = final_url or response_url

    # page.locator() returns a mock locator
    locator = MagicMock()
    locator.count = AsyncMock(return_value=0)
    page.locator = MagicMock(return_value=locator)

    return page


def _page_with_2fa(page):
    """Configure page mock so a 2FA input is detected."""
    otp_locator = MagicMock()
    otp_locator.count = AsyncMock(return_value=1)
    # Make the first locator call (otp selector) return the found one,
    # others return zero.
    def locator_side_effect(selector):
        loc = MagicMock()
        if "otp" in selector or "totp" in selector or "2fa" in selector or "two-factor" in selector:
            loc.count = AsyncMock(return_value=1)
        else:
            loc.count = AsyncMock(return_value=0)
        return loc
    page.locator = MagicMock(side_effect=locator_side_effect)
    return page


@pytest.fixture
def validator():
    return SessionValidator()


@pytest.fixture
def validator_custom():
    return SessionValidator(protected_paths={"custom_portal": "/auth/sso"})


# ── SessionValidationResult dataclass ────────────────────────────────────────


def test_result_defaults():
    r = SessionValidationResult(valid=True, needs_login=False, needs_2fa=False)
    assert r.error is None
    assert r.details == {}


def test_result_with_details():
    r = SessionValidationResult(
        valid=False, needs_login=True, needs_2fa=False,
        error="expired", details={"cookie_count": 0},
    )
    assert r.error == "expired"
    assert r.details["cookie_count"] == 0


# ── check_cookies ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_cookies_present(validator):
    cookies = [
        {"name": "session_id", "value": "abc123", "domain": ".greenhouse.io"},
        {"name": "_ga", "value": "xyz", "domain": ".greenhouse.io"},
    ]
    page = _make_page(cookies=cookies)
    assert await validator.check_cookies(page, "greenhouse") is True


@pytest.mark.asyncio
async def test_check_cookies_empty(validator):
    page = _make_page(cookies=[])
    assert await validator.check_cookies(page, "greenhouse") is False


# ── probe_endpoint ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_probe_endpoint_ok(validator):
    """200 OK on protected endpoint → session valid."""
    page = _make_page(
        cookies=[{"name": "sid", "value": "x"}],
        response_status=200,
        response_url="https://boards.greenhouse.io/techco/jobs/123",
    )
    result = await validator.probe_endpoint(page, "https://boards.greenhouse.io/techco/jobs/123", "greenhouse")
    assert result.valid is True
    assert result.needs_login is False


@pytest.mark.asyncio
async def test_probe_endpoint_redirect(validator):
    """Redirect to login page → session expired."""
    page = _make_page(
        cookies=[{"name": "sid", "value": "x"}],
        response_status=200,
        response_url="https://boards.greenhouse.io/login",
        final_url="https://boards.greenhouse.io/login",
    )
    result = await validator.probe_endpoint(page, "https://boards.greenhouse.io/techco/jobs/123", "greenhouse")
    assert result.valid is False
    assert result.needs_login is True


@pytest.mark.asyncio
async def test_probe_endpoint_401(validator):
    """401 response → needs re-auth."""
    page = _make_page(
        cookies=[{"name": "sid", "value": "x"}],
        response_status=401,
        response_url="https://boards.greenhouse.io/techco/jobs/123",
    )
    result = await validator.probe_endpoint(page, "https://boards.greenhouse.io/techco/jobs/123", "greenhouse")
    assert result.valid is False


@pytest.mark.asyncio
async def test_probe_endpoint_403(validator):
    """403 response → needs re-auth."""
    page = _make_page(
        cookies=[{"name": "sid", "value": "x"}],
        response_status=403,
        response_url="https://boards.greenhouse.io/techco/jobs/123",
    )
    result = await validator.probe_endpoint(page, "https://boards.greenhouse.io/techco/jobs/123", "greenhouse")
    assert result.valid is False


@pytest.mark.asyncio
async def test_custom_protected_paths(validator_custom):
    """Custom protected_paths mapping is used for unknown portal types."""
    page = _make_page(
        cookies=[{"name": "sid", "value": "x"}],
        response_status=200,
        response_url="https://app.example.com/auth/sso",
        final_url="https://app.example.com/auth/sso",
    )
    result = await validator_custom.probe_endpoint(page, "https://app.example.com/dashboard", "custom_portal")
    # Verify goto was called with the custom protected path
    call_args = page.goto.call_args
    assert "/auth/sso" in call_args[0][0]


# ── validate (full pipeline) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_valid_session(validator):
    """Cookies present + 200 OK + no 2FA → fully valid."""
    page = _make_page(
        cookies=[{"name": "sid", "value": "x"}],
        response_status=200,
        response_url="https://boards.greenhouse.io/techco/jobs/123",
    )
    result = await validator.validate("https://boards.greenhouse.io/techco/jobs/123", "greenhouse", page)
    assert result.valid is True
    assert result.needs_login is False
    assert result.needs_2fa is False


@pytest.mark.asyncio
async def test_validate_expired_cookies(validator):
    """Empty cookies → needs_login=True, valid=False."""
    page = _make_page(cookies=[])
    result = await validator.validate("https://boards.greenhouse.io/techco/jobs/123", "greenhouse", page)
    assert result.valid is False
    assert result.needs_login is True


@pytest.mark.asyncio
async def test_validate_login_redirect(validator):
    """Cookies present but probe redirects to login → needs_login=True."""
    page = _make_page(
        cookies=[{"name": "sid", "value": "x"}],
        response_status=200,
        response_url="https://boards.greenhouse.io/login",
        final_url="https://boards.greenhouse.io/login",
    )
    result = await validator.validate("https://boards.greenhouse.io/techco/jobs/123", "greenhouse", page)
    assert result.valid is False
    assert result.needs_login is True


@pytest.mark.asyncio
async def test_validate_2fa_detected(validator):
    """2FA input detected on page → needs_2fa=True."""
    page = _make_page(
        cookies=[{"name": "sid", "value": "x"}],
        response_status=200,
        response_url="https://boards.greenhouse.io/techco/jobs/123",
    )
    page = _page_with_2fa(page)
    result = await validator.validate("https://boards.greenhouse.io/techco/jobs/123", "greenhouse", page)
    assert result.needs_2fa is True


@pytest.mark.asyncio
async def test_validate_empty_cookie_jar(validator):
    """Empty cookie jar → needs_login=True regardless of probe."""
    page = _make_page(cookies=[])
    result = await validator.validate("https://myworkday.com/inst/123", "workday", page)
    assert result.needs_login is True
    assert result.valid is False


@pytest.mark.asyncio
async def test_validate_exception_handling(validator):
    """Unexpected exception → returns error result, doesn't crash."""
    page = MagicMock()
    page.context = MagicMock()
    page.context.cookies = AsyncMock(side_effect=RuntimeError("browser crashed"))

    result = await validator.validate("https://example.com/job", "greenhouse", page)
    assert result.valid is False
    assert result.error is not None
    assert "browser crashed" in result.error


# ── Protected paths mapping ───────────────────────────────────────────────────


def test_default_protected_paths():
    v = SessionValidator()
    assert v._protected_paths["greenhouse"] == "/login"
    assert v._protected_paths["lever"] == "/login"
    assert v._protected_paths["workday"] == "/wdhsso"
    assert v._protected_paths["default"] == "/login"


def test_protected_paths_merge():
    """Custom paths merge with defaults, not replace."""
    v = SessionValidator(protected_paths={"myats": "/sso"})
    assert v._protected_paths["myats"] == "/sso"
    assert v._protected_paths["greenhouse"] == "/login"  # default still there


def test_validate_sync_valid():
    """Test validate_sync on a sync-style page mock."""
    page = MagicMock()
    page.context.cookies.return_value = [{"name": "sid", "value": "123"}]
    resp = MagicMock()
    resp.status = 200
    resp.url = "https://boards.greenhouse.io/techco/jobs/123"
    page.goto.return_value = resp
    page.url = "https://boards.greenhouse.io/techco/jobs/123"
    locator = MagicMock()
    locator.count.return_value = 0
    page.locator.return_value = locator

    v = SessionValidator()
    result = v.validate_sync("https://boards.greenhouse.io/techco/jobs/123", "greenhouse", page)
    assert result.valid is True
    assert result.needs_login is False


def test_validate_sync_empty_cookies():
    """Test validate_sync rejects empty cookies."""
    page = MagicMock()
    page.context.cookies.return_value = []

    v = SessionValidator()
    result = v.validate_sync("https://boards.greenhouse.io/techco/jobs/123", "greenhouse", page)
    assert result.valid is False
    assert result.needs_login is True

