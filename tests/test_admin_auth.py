"""Admin auth cookie imzalama testleri."""
import time
import hmac
import hashlib

SECRET_KEY = "test-secret"
SESSION_TTL = 28800
COOKIE_NAME = "mssradmon_session"


def _sign_cookie(username: str, secret: str) -> str:
    ts = str(int(time.time()))
    msg = f"{username}:{ts}"
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}:{sig}"


def _verify_cookie(value: str, secret: str, ttl: int = SESSION_TTL) -> str | None:
    try:
        parts = value.split(":")
        if len(parts) != 3:
            return None
        username, ts_str, sig = parts
        msg = f"{username}:{ts_str}"
        expected = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        if int(time.time()) - int(ts_str) > ttl:
            return None
        return username
    except Exception:
        return None


def test_sign_and_verify():
    token = _sign_cookie("mssadmin", SECRET_KEY)
    assert _verify_cookie(token, SECRET_KEY) == "mssadmin"


def test_wrong_secret_rejected():
    token = _sign_cookie("mssadmin", SECRET_KEY)
    assert _verify_cookie(token, "wrong-secret") is None


def test_tampered_token_rejected():
    token = _sign_cookie("mssadmin", SECRET_KEY)
    parts = token.split(":")
    parts[0] = "hacker"
    assert _verify_cookie(":".join(parts), SECRET_KEY) is None


def test_expired_token_rejected():
    username = "mssadmin"
    ts = str(int(time.time()) - SESSION_TTL - 1)
    msg = f"{username}:{ts}"
    sig = hmac.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
    token = f"{msg}:{sig}"
    assert _verify_cookie(token, SECRET_KEY) is None


def test_malformed_token_rejected():
    assert _verify_cookie("notavalidtoken", SECRET_KEY) is None
    assert _verify_cookie("", SECRET_KEY) is None
    assert _verify_cookie("a:b", SECRET_KEY) is None
