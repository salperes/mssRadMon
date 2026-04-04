"""SSL endpoint entegrasyon testleri."""
import pytest
from httpx import AsyncClient

from app.auth import _sign_cookie, COOKIE_NAME


def _admin_cookies(username: str = "mssadmin") -> dict:
    return {COOKIE_NAME: _sign_cookie(username)}


class TestSslStatus:

    @pytest.mark.asyncio
    async def test_status_requires_admin(self, test_client: AsyncClient):
        res = await test_client.get("/api/ssl/status")
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_status_returns_fields(self, test_client: AsyncClient):
        res = await test_client.get("/api/ssl/status", cookies=_admin_cookies())
        assert res.status_code == 200
        data = res.json()
        assert "ca_trusted" in data
        assert "has_cert" in data
        assert "ssl_enabled" in data
        assert "ca_server" in data
        assert data["ssl_enabled"] is False
        assert data["has_cert"] is False


class TestSslTrustCa:

    @pytest.mark.asyncio
    async def test_trust_ca_requires_admin(self, test_client: AsyncClient):
        res = await test_client.post("/api/ssl/trust-ca")
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_trust_ca_no_url(self, test_client: AsyncClient):
        res = await test_client.post("/api/ssl/trust-ca", cookies=_admin_cookies())
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is False


class TestSslRequest:

    @pytest.mark.asyncio
    async def test_request_requires_admin(self, test_client: AsyncClient):
        res = await test_client.post("/api/ssl/request", json={"hostname": "test"})
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_request_empty_hostname(self, test_client: AsyncClient):
        res = await test_client.post(
            "/api/ssl/request",
            json={"hostname": ""},
            cookies=_admin_cookies(),
        )
        assert res.status_code == 400

    @pytest.mark.asyncio
    async def test_request_no_ca_url(self, test_client: AsyncClient):
        res = await test_client.post(
            "/api/ssl/request",
            json={"hostname": "test.mss.local"},
            cookies=_admin_cookies(),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is False

    @pytest.mark.asyncio
    async def test_viewer_cannot_access(self, test_client: AsyncClient):
        await test_client.post(
            "/api/users",
            json={"username": "sslviewer", "password": "Pass1", "role": "viewer"},
            cookies=_admin_cookies(),
        )
        res = await test_client.get(
            "/api/ssl/status",
            cookies={COOKIE_NAME: _sign_cookie("sslviewer")},
        )
        assert res.status_code == 403
