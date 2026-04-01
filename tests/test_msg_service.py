"""app/msg_service.py unit testleri."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app import msg_service


def _make_resp(data: dict):
    """urllib.request.urlopen context manager mock'u."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(data).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestSendMail:
    def test_returns_message_id_on_success(self):
        resp = _make_resp({"success": True, "messageId": "abc-123"})
        with patch("urllib.request.urlopen", return_value=resp):
            result = msg_service.send_mail(
                "http://localhost:3501", "key123",
                ["test@example.com"], "", "HIGH", 0.55, "GammaScout-01", ""
            )
        assert result == "abc-123"

    def test_returns_none_on_empty_to_list(self):
        result = msg_service.send_mail(
            "http://localhost:3501", "key123", [], "", "HIGH", 0.55, "GammaScout-01", ""
        )
        assert result is None

    def test_returns_none_on_missing_url(self):
        result = msg_service.send_mail(
            "", "key123", ["a@b.com"], "", "HIGH", 0.55, "GammaScout-01", ""
        )
        assert result is None

    def test_returns_none_on_missing_api_key(self):
        result = msg_service.send_mail(
            "http://localhost:3501", "", ["a@b.com"], "", "HIGH", 0.55, "GammaScout-01", ""
        )
        assert result is None

    def test_returns_none_on_connection_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            result = msg_service.send_mail(
                "http://localhost:3501", "key123",
                ["a@b.com"], "", "HIGH", 0.55, "GammaScout-01", ""
            )
        assert result is None

    def test_returns_none_when_success_false(self):
        resp = _make_resp({"success": False, "error": "Invalid key"})
        with patch("urllib.request.urlopen", return_value=resp):
            result = msg_service.send_mail(
                "http://localhost:3501", "key123",
                ["a@b.com"], "", "HIGH", 0.55, "GammaScout-01", ""
            )
        assert result is None

    def test_includes_reply_to_when_set(self):
        resp = _make_resp({"success": True, "messageId": "x1"})
        captured = {}

        def fake_urlopen(req, **kwargs):
            import json as _json
            captured["body"] = _json.loads(req.data.decode())
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            msg_service.send_mail(
                "http://localhost:3501", "key123",
                ["a@b.com"], "noreply@test.com", "HIGH", 0.55, "GammaScout-01", ""
            )
        assert captured["body"].get("replyTo") == "noreply@test.com"

    def test_omits_reply_to_when_empty(self):
        resp = _make_resp({"success": True, "messageId": "x2"})
        captured = {}

        def fake_urlopen(req, **kwargs):
            import json as _json
            captured["body"] = _json.loads(req.data.decode())
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            msg_service.send_mail(
                "http://localhost:3501", "key123",
                ["a@b.com"], "", "HIGH", 0.55, "GammaScout-01", ""
            )
        assert "replyTo" not in captured["body"]


class TestSendWhatsapp:
    def test_returns_message_ids_on_success(self):
        resp = _make_resp({"success": True, "messageId": "wa-001"})
        with patch("urllib.request.urlopen", return_value=resp):
            result = msg_service.send_whatsapp(
                "http://localhost:3501", "key123",
                ["905551234567"], "HIGH", 0.55, "GammaScout-01"
            )
        assert result == ["wa-001"]

    def test_returns_empty_on_empty_phone_list(self):
        result = msg_service.send_whatsapp(
            "http://localhost:3501", "key123", [], "HIGH", 0.55, "GammaScout-01"
        )
        assert result == []

    def test_returns_empty_on_missing_url(self):
        result = msg_service.send_whatsapp(
            "", "key123", ["905551234567"], "HIGH", 0.55, "GammaScout-01"
        )
        assert result == []

    def test_returns_none_entries_on_failure(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = msg_service.send_whatsapp(
                "http://localhost:3501", "key123",
                ["905551234567", "905559876543"], "HIGH", 0.55, "GammaScout-01"
            )
        assert result == [None, None]

    def test_sends_one_request_per_phone(self):
        call_count = 0
        resp = _make_resp({"success": True, "messageId": "wa-x"})

        def fake_urlopen(req, **kwargs):
            nonlocal call_count
            call_count += 1
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            msg_service.send_whatsapp(
                "http://localhost:3501", "key123",
                ["905551111111", "905552222222", "905553333333"],
                "HIGH", 0.55, "GammaScout-01"
            )
        assert call_count == 3


class TestHealthCheck:
    def test_returns_health_data(self):
        data = {"status": "ok", "version": "0.2.18", "uptime": 3600}
        resp = _make_resp(data)
        with patch("urllib.request.urlopen", return_value=resp):
            result = msg_service.health_check("http://localhost:3501")
        assert result == data

    def test_returns_none_on_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = msg_service.health_check("http://localhost:3501")
        assert result is None
