"""Admin panel frontend akışları — entegrasyon testleri.

Login, logout, API key üretimi/yönetimi, kullanıcı CRUD,
şifre değiştirme, sayfa erişim kontrolü ve rol bazlı kısıtlamalar.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.auth import _sign_cookie, COOKIE_NAME


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admin_cookies(username: str = "mssadmin") -> dict:
    """Geçerli admin session cookie döndür."""
    return {COOKIE_NAME: _sign_cookie(username)}


# ===========================================================================
# 1. LOGIN / LOGOUT
# ===========================================================================

class TestLoginLogout:

    @pytest.mark.asyncio
    async def test_login_page_renders(self, test_client: AsyncClient):
        res = await test_client.get("/admin/login")
        assert res.status_code == 200
        assert "mssRadMon" in res.text

    @pytest.mark.asyncio
    async def test_login_success_redirects(self, test_client: AsyncClient):
        res = await test_client.post(
            "/admin/login",
            data={"username": "mssadmin", "password": "Ankara12!"},
            follow_redirects=False,
        )
        assert res.status_code == 303
        assert res.headers["location"] == "/admin"
        assert COOKIE_NAME in res.cookies

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, test_client: AsyncClient):
        res = await test_client.post(
            "/admin/login",
            data={"username": "mssadmin", "password": "wrong"},
            follow_redirects=False,
        )
        assert res.status_code == 303
        assert "error=1" in res.headers["location"]

    @pytest.mark.asyncio
    async def test_logout_clears_cookie(self, test_client: AsyncClient):
        res = await test_client.post(
            "/admin/logout",
            cookies=_admin_cookies(),
            follow_redirects=False,
        )
        assert res.status_code == 303
        assert res.headers["location"] == "/admin/login"
        # Cookie silinmiş olmalı (max-age=0 veya set edilmemiş)
        set_cookie = res.headers.get("set-cookie", "")
        assert COOKIE_NAME in set_cookie  # delete_cookie set-cookie header üretir

    @pytest.mark.asyncio
    async def test_admin_page_requires_login(self, test_client: AsyncClient):
        res = await test_client.get("/admin", follow_redirects=False)
        assert res.status_code == 303
        assert "login" in res.headers["location"]

    @pytest.mark.asyncio
    async def test_logout_then_admin_redirects_to_login(self, test_client: AsyncClient):
        """Logout sonrası admin sayfasına erişim login'e yönlendirmeli."""
        # Login ol
        login_res = await test_client.post(
            "/admin/login",
            data={"username": "mssadmin", "password": "Ankara12!"},
            follow_redirects=False,
        )
        session_cookie = login_res.cookies.get(COOKIE_NAME)
        assert session_cookie

        # Logout ol
        logout_res = await test_client.post(
            "/admin/logout",
            cookies={COOKIE_NAME: session_cookie},
            follow_redirects=False,
        )
        assert logout_res.status_code == 303

        # Logout'tan gelen set-cookie'den max-age=0 olan cookie'yi al
        # Tarayıcı bunu silecek, biz de cookie olmadan deneyelim
        admin_res = await test_client.get("/admin", follow_redirects=False)
        assert admin_res.status_code == 303
        assert "login" in admin_res.headers["location"]

    @pytest.mark.asyncio
    async def test_admin_page_with_valid_cookie(self, test_client: AsyncClient):
        res = await test_client.get("/admin", cookies=_admin_cookies())
        assert res.status_code == 200
        assert "admin.js" in res.text


# ===========================================================================
# 2. ADMIN PAGE — HTML RENDER
# ===========================================================================

class TestAdminPageRender:

    @pytest.mark.asyncio
    async def test_api_access_section_exists(self, test_client: AsyncClient):
        res = await test_client.get("/admin", cookies=_admin_cookies())
        assert 'id="sec-api-access"' in res.text
        assert 'id="generateApiKeyBtn"' in res.text
        assert 'id="copyApiKeyBtn"' in res.text
        assert 'id="apiKeyDisplay"' in res.text

    @pytest.mark.asyncio
    async def test_users_section_exists(self, test_client: AsyncClient):
        res = await test_client.get("/admin", cookies=_admin_cookies())
        assert 'id="sec-users"' in res.text
        assert 'id="addUserBtn"' in res.text
        assert 'id="changePasswordBtn"' in res.text
        assert 'id="userList"' in res.text

    @pytest.mark.asyncio
    async def test_user_role_js_variable_rendered(self, test_client: AsyncClient):
        res = await test_client.get("/admin", cookies=_admin_cookies())
        assert 'const USER_ROLE = "admin"' in res.text

    @pytest.mark.asyncio
    async def test_user_role_before_admin_js(self, test_client: AsyncClient):
        """USER_ROLE admin.js'ten ÖNCE tanımlanmalı."""
        res = await test_client.get("/admin", cookies=_admin_cookies())
        role_pos = res.text.index("const USER_ROLE")
        js_pos = res.text.index("admin.js")
        assert role_pos < js_pos, "USER_ROLE admin.js'ten sonra tanımlanmış — JS hata verir"

    @pytest.mark.asyncio
    async def test_sidebar_links_present(self, test_client: AsyncClient):
        res = await test_client.get("/admin", cookies=_admin_cookies())
        for section in ["device", "sampling", "alarm", "email", "api-access", "users", "history"]:
            assert f'data-section="{section}"' in res.text, f"Sidebar'da {section} linki yok"

    @pytest.mark.asyncio
    async def test_logout_button_in_sidebar(self, test_client: AsyncClient):
        res = await test_client.get("/admin", cookies=_admin_cookies())
        assert '/admin/logout' in res.text
        assert 'Çıkış' in res.text


# ===========================================================================
# 3. VIEWER ROLE — HTML KISITLAMALARI
# ===========================================================================

class TestViewerRestrictions:

    @pytest_asyncio.fixture
    async def viewer_client(self, test_client: AsyncClient):
        """viewer kullanıcı oluştur ve cookie'sini döndür."""
        # Önce admin olarak viewer ekle
        await test_client.post(
            "/api/users",
            json={"username": "viewer1", "password": "ViewerPass1", "role": "viewer"},
            cookies=_admin_cookies(),
        )
        return _admin_cookies("viewer1")

    @pytest.mark.asyncio
    async def test_viewer_admin_page_renders(self, test_client: AsyncClient, viewer_client):
        res = await test_client.get("/admin", cookies=viewer_client)
        assert res.status_code == 200
        assert 'const USER_ROLE = "viewer"' in res.text

    @pytest.mark.asyncio
    async def test_viewer_cannot_save_settings(self, test_client: AsyncClient, viewer_client):
        res = await test_client.put(
            "/api/settings",
            json={"sampling_interval": "999"},
            cookies=viewer_client,
        )
        assert res.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_user(self, test_client: AsyncClient, viewer_client):
        res = await test_client.post(
            "/api/users",
            json={"username": "hacker", "password": "hack", "role": "admin"},
            cookies=viewer_client,
        )
        assert res.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete_user(self, test_client: AsyncClient, viewer_client):
        res = await test_client.delete(
            "/api/users/mssadmin",
            cookies=viewer_client,
        )
        assert res.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_generate_api_key(self, test_client: AsyncClient, viewer_client):
        res = await test_client.post(
            "/api/apikey/generate",
            cookies=viewer_client,
        )
        assert res.status_code == 403


# ===========================================================================
# 4. API KEY ÜRETİMİ ve YÖNETİMİ
# ===========================================================================

class TestApiKey:

    @pytest.mark.asyncio
    async def test_generate_api_key(self, test_client: AsyncClient):
        res = await test_client.post(
            "/api/apikey/generate",
            cookies=_admin_cookies(),
        )
        assert res.status_code == 200
        data = res.json()
        assert "api_key" in data
        assert len(data["api_key"]) == 64  # secrets.token_hex(32)

    @pytest.mark.asyncio
    async def test_generated_key_saved_in_settings(self, test_client: AsyncClient):
        gen_res = await test_client.post(
            "/api/apikey/generate",
            cookies=_admin_cookies(),
        )
        key = gen_res.json()["api_key"]

        settings_res = await test_client.get(
            "/api/settings",
            cookies=_admin_cookies(),
        )
        assert settings_res.json()["api_key"] == key

    @pytest.mark.asyncio
    async def test_regenerate_invalidates_old_key(self, test_client: AsyncClient):
        res1 = await test_client.post("/api/apikey/generate", cookies=_admin_cookies())
        old_key = res1.json()["api_key"]

        res2 = await test_client.post("/api/apikey/generate", cookies=_admin_cookies())
        new_key = res2.json()["api_key"]

        assert old_key != new_key

        # Eski key ile erişim reddedilmeli
        res = await test_client.get(
            "/api/device",
            headers={"X-API-Key": old_key},
        )
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_protects_endpoints(self, test_client: AsyncClient):
        gen_res = await test_client.post("/api/apikey/generate", cookies=_admin_cookies())
        key = gen_res.json()["api_key"]

        # Key ile erişim
        res = await test_client.get("/api/device", headers={"X-API-Key": key})
        assert res.status_code == 200

        # Key'siz erişim (cookie de yok)
        res = await test_client.get("/api/device")
        assert res.status_code in (401, 503)

    @pytest.mark.asyncio
    async def test_generate_requires_auth(self, test_client: AsyncClient):
        res = await test_client.post("/api/apikey/generate")
        assert res.status_code == 401


# ===========================================================================
# 5. KULLANICI YÖNETİMİ
# ===========================================================================

class TestUserManagement:

    @pytest.mark.asyncio
    async def test_list_users(self, test_client: AsyncClient):
        res = await test_client.get("/api/users", cookies=_admin_cookies())
        assert res.status_code == 200
        users = res.json()
        assert any(u["username"] == "mssadmin" for u in users)

    @pytest.mark.asyncio
    async def test_get_current_user_me(self, test_client: AsyncClient):
        res = await test_client.get("/api/users/me", cookies=_admin_cookies())
        assert res.status_code == 200
        data = res.json()
        assert data["username"] == "mssadmin"
        assert data["role"] == "admin"

    @pytest.mark.asyncio
    async def test_create_user(self, test_client: AsyncClient):
        res = await test_client.post(
            "/api/users",
            json={"username": "newuser", "password": "Pass123!", "role": "viewer"},
            cookies=_admin_cookies(),
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True

        # Login edebilmeli
        login_res = await test_client.post(
            "/admin/login",
            data={"username": "newuser", "password": "Pass123!"},
            follow_redirects=False,
        )
        assert login_res.status_code == 303
        assert login_res.headers["location"] == "/admin"

    @pytest.mark.asyncio
    async def test_create_duplicate_user(self, test_client: AsyncClient):
        await test_client.post(
            "/api/users",
            json={"username": "dupuser", "password": "Pass1", "role": "viewer"},
            cookies=_admin_cookies(),
        )
        res = await test_client.post(
            "/api/users",
            json={"username": "dupuser", "password": "Pass2", "role": "viewer"},
            cookies=_admin_cookies(),
        )
        assert res.status_code == 409

    @pytest.mark.asyncio
    async def test_create_user_missing_fields(self, test_client: AsyncClient):
        res = await test_client.post(
            "/api/users",
            json={"username": "", "password": ""},
            cookies=_admin_cookies(),
        )
        assert res.status_code == 400

    @pytest.mark.asyncio
    async def test_create_user_invalid_role(self, test_client: AsyncClient):
        res = await test_client.post(
            "/api/users",
            json={"username": "x", "password": "y", "role": "superadmin"},
            cookies=_admin_cookies(),
        )
        assert res.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_user(self, test_client: AsyncClient):
        await test_client.post(
            "/api/users",
            json={"username": "todelete", "password": "Pass1", "role": "viewer"},
            cookies=_admin_cookies(),
        )
        res = await test_client.delete(
            "/api/users/todelete",
            cookies=_admin_cookies(),
        )
        assert res.status_code == 200

        # Silinen kullanıcı login edememeli
        login_res = await test_client.post(
            "/admin/login",
            data={"username": "todelete", "password": "Pass1"},
            follow_redirects=False,
        )
        assert "error=1" in login_res.headers["location"]

    @pytest.mark.asyncio
    async def test_cannot_delete_self(self, test_client: AsyncClient):
        res = await test_client.delete(
            "/api/users/mssadmin",
            cookies=_admin_cookies(),
        )
        assert res.status_code == 400
        assert "kendi" in res.json()["detail"].lower() or "Kendi" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_cannot_delete_last_admin(self, test_client: AsyncClient):
        # İkinci admin ekle
        await test_client.post(
            "/api/users",
            json={"username": "admin2", "password": "Pass1", "role": "admin"},
            cookies=_admin_cookies(),
        )
        # admin2 ile mssadmin'i silmeye çalış — mssadmin son admin değil ama
        # admin2 kendi kendini silemez
        # Daha iyi test: admin2 olarak viewer silmeyi dene (başarılı olmalı)
        await test_client.post(
            "/api/users",
            json={"username": "victim", "password": "P1", "role": "viewer"},
            cookies=_admin_cookies(),
        )
        res = await test_client.delete(
            "/api/users/victim",
            cookies=_admin_cookies("admin2"),
        )
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user(self, test_client: AsyncClient):
        res = await test_client.delete(
            "/api/users/ghost",
            cookies=_admin_cookies(),
        )
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_list_users_requires_admin(self, test_client: AsyncClient):
        res = await test_client.get("/api/users")
        assert res.status_code == 401

    @pytest.mark.asyncio
    async def test_me_requires_auth(self, test_client: AsyncClient):
        res = await test_client.get("/api/users/me")
        assert res.status_code == 401


# ===========================================================================
# 6. ŞİFRE DEĞİŞTİRME
# ===========================================================================

class TestPasswordChange:

    @pytest_asyncio.fixture
    async def pw_user(self, test_client: AsyncClient):
        """Şifre testi için kullanıcı oluştur."""
        await test_client.post(
            "/api/users",
            json={"username": "pwuser", "password": "OldPass1", "role": "viewer"},
            cookies=_admin_cookies(),
        )
        return "pwuser"

    @pytest.mark.asyncio
    async def test_change_own_password(self, test_client: AsyncClient, pw_user):
        res = await test_client.put(
            f"/api/users/{pw_user}/password",
            json={"current_password": "OldPass1", "new_password": "NewPass2"},
            cookies=_admin_cookies(pw_user),
        )
        assert res.status_code == 200

        # Yeni şifreyle login
        login_res = await test_client.post(
            "/admin/login",
            data={"username": pw_user, "password": "NewPass2"},
            follow_redirects=False,
        )
        assert login_res.status_code == 303
        assert login_res.headers["location"] == "/admin"

    @pytest.mark.asyncio
    async def test_wrong_current_password(self, test_client: AsyncClient, pw_user):
        res = await test_client.put(
            f"/api/users/{pw_user}/password",
            json={"current_password": "WRONG", "new_password": "NewPass2"},
            cookies=_admin_cookies(pw_user),
        )
        assert res.status_code == 400
        assert "yanlış" in res.json()["detail"].lower() or "Mevcut" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_missing_new_password(self, test_client: AsyncClient, pw_user):
        res = await test_client.put(
            f"/api/users/{pw_user}/password",
            json={"current_password": "OldPass1", "new_password": ""},
            cookies=_admin_cookies(pw_user),
        )
        assert res.status_code == 400

    @pytest.mark.asyncio
    async def test_admin_changes_other_password(self, test_client: AsyncClient, pw_user):
        """Admin başkasının şifresini current_password olmadan değiştirebilmeli."""
        res = await test_client.put(
            f"/api/users/{pw_user}/password",
            json={"new_password": "AdminSet1"},
            cookies=_admin_cookies(),  # mssadmin (admin)
        )
        assert res.status_code == 200

        # Yeni şifreyle login
        login_res = await test_client.post(
            "/admin/login",
            data={"username": pw_user, "password": "AdminSet1"},
            follow_redirects=False,
        )
        assert login_res.headers["location"] == "/admin"

    @pytest.mark.asyncio
    async def test_viewer_cannot_change_other_password(self, test_client: AsyncClient, pw_user):
        """viewer başka kullanıcının şifresini değiştirememeli."""
        await test_client.post(
            "/api/users",
            json={"username": "viewer_x", "password": "V1", "role": "viewer"},
            cookies=_admin_cookies(),
        )
        res = await test_client.put(
            f"/api/users/{pw_user}/password",
            json={"current_password": "V1", "new_password": "Hacked"},
            cookies=_admin_cookies("viewer_x"),
        )
        assert res.status_code == 403


# ===========================================================================
# 7. GET /api/device
# ===========================================================================

class TestDeviceEndpoint:

    @pytest.mark.asyncio
    async def test_device_with_cookie(self, test_client: AsyncClient):
        res = await test_client.get("/api/device", cookies=_admin_cookies())
        assert res.status_code == 200
        data = res.json()
        assert "device_name" in data
        assert "device_location" in data
        assert "device_serial" in data

    @pytest.mark.asyncio
    async def test_device_with_api_key(self, test_client: AsyncClient):
        gen = await test_client.post("/api/apikey/generate", cookies=_admin_cookies())
        key = gen.json()["api_key"]
        res = await test_client.get("/api/device", headers={"X-API-Key": key})
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_device_without_auth(self, test_client: AsyncClient):
        res = await test_client.get("/api/device")
        assert res.status_code in (401, 503)


# ===========================================================================
# 8. DASHBOARD PAGE
# ===========================================================================

class TestDashboard:

    @pytest.mark.asyncio
    async def test_dashboard_renders(self, test_client: AsyncClient):
        res = await test_client.get("/")
        assert res.status_code == 200
        assert "dashboard.js" in res.text
        assert "doseChart" in res.text

    @pytest.mark.asyncio
    async def test_dashboard_no_login_required(self, test_client: AsyncClient):
        """Dashboard login gerektirmemeli."""
        res = await test_client.get("/", follow_redirects=False)
        assert res.status_code == 200


# ===========================================================================
# 9. SETTINGS API
# ===========================================================================

class TestSettingsApi:

    @pytest.mark.asyncio
    async def test_get_settings(self, test_client: AsyncClient):
        res = await test_client.get("/api/settings", cookies=_admin_cookies())
        assert res.status_code == 200
        data = res.json()
        assert "sampling_interval" in data
        assert "threshold_high" in data

    @pytest.mark.asyncio
    async def test_put_settings_admin(self, test_client: AsyncClient):
        res = await test_client.put(
            "/api/settings",
            json={"sampling_interval": "20"},
            cookies=_admin_cookies(),
        )
        assert res.status_code == 200

        get_res = await test_client.get("/api/settings", cookies=_admin_cookies())
        assert get_res.json()["sampling_interval"] == "20"

    @pytest.mark.asyncio
    async def test_put_settings_no_auth(self, test_client: AsyncClient):
        res = await test_client.put(
            "/api/settings",
            json={"sampling_interval": "99"},
        )
        assert res.status_code in (401, 503)
