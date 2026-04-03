"""Admin auth cookie imzalama testleri."""
import time
import hmac
import hashlib
import pytest

from app.auth import _sign_cookie, _verify_cookie, _SECRET_KEY, _SESSION_TTL


def test_sign_and_verify():
    token = _sign_cookie("mssadmin")
    assert _verify_cookie(token) == "mssadmin"


def test_wrong_secret_rejected():
    token = _sign_cookie("mssadmin")
    # İmzayı bozmak için token'ı manipüle et
    parts = token.split(":")
    parts[2] = "badsig"
    assert _verify_cookie(":".join(parts)) is None


def test_tampered_token_rejected():
    token = _sign_cookie("mssadmin")
    parts = token.split(":")
    parts[0] = "hacker"
    assert _verify_cookie(":".join(parts)) is None


def test_expired_token_rejected():
    username = "mssadmin"
    ts = str(int(time.time()) - _SESSION_TTL - 1)
    msg = f"{username}:{ts}"
    sig = hmac.new(_SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
    token = f"{msg}:{sig}"
    assert _verify_cookie(token) is None


def test_malformed_token_rejected():
    assert _verify_cookie("notavalidtoken") is None
    assert _verify_cookie("") is None
    assert _verify_cookie("a:b") is None
