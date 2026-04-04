"""mssRadMon — FastAPI uygulama giriş noktası."""
import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.alarm import AlarmManager
from app.auth import (
    _hash_password,
    _sign_cookie,
    _verify_cookie,
    _SESSION_TTL,
    COOKIE_NAME,
    get_current_user,
    require_admin,
    require_admin_or_apikey,
    verify_api_key,
)
from app.config import Config
from app.db import Database
from app.remote_log import RemoteLogForwarder
from app.routers import admin, api, ws
from app.serial_reader import GammaScoutReader, Reading
from app.shift import ShiftManager
from app.ssl import SslManager
from app import wifi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("MSSRADMON_DB_PATH", "data/readings.db")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


def create_app() -> FastAPI:
    """FastAPI uygulamasını oluştur."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        db_path = os.environ.get("MSSRADMON_DB_PATH", DB_PATH)
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        db = Database(db_path)
        await db.init()
        config = Config(db)
        await config.init()

        # users tablosu boşsa mssadmin'i ekle (ilk kurulum)
        user_count = await db.fetch_one("SELECT COUNT(*) as n FROM users")
        if user_count["n"] == 0:
            pw_hash = _hash_password("Ankara12!", "mssadmin")
            await db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("mssadmin", pw_hash, "admin"),
            )
            logger.info("İlk kullanıcı oluşturuldu: mssadmin (admin)")

        alarm_manager = AlarmManager(db=db, config=config)
        await alarm_manager.init()

        shift_manager = ShiftManager(db=db, config=config)
        await shift_manager.close_stale()

        remote_log = RemoteLogForwarder(db=db, config=config)

        reader = GammaScoutReader()

        # Kümülatif dozu DB'deki son değerden devam ettir
        last_row = await db.fetch_one(
            "SELECT cumulative_dose FROM readings ORDER BY id DESC LIMIT 1"
        )
        if last_row:
            reader._cumulative_dose = last_row["cumulative_dose"]

        # App state'e ata
        app.state.db = db
        app.state.config = config
        app.state.alarm = alarm_manager
        app.state.remote_log = remote_log
        app.state.shift_manager = shift_manager
        ssl_manager = SslManager(config=config)
        app.state.ssl_manager = ssl_manager
        app.state.reader = reader
        app.state.ws_clients = set()

        async def on_reading(reading: Reading):
            """Yeni okuma geldiğinde çağrılır."""
            # Seri numarasını config'e kaydet (bir kez)
            if reader.serial_number:
                current_sn = await config.get("device_serial")
                if current_sn != reader.serial_number:
                    await config.set("device_serial", reader.serial_number)
            row_id = await db.execute(
                "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
                (reading.timestamp, reading.dose_rate, reading.cumulative_dose),
            )
            # Alarm kontrolü
            await alarm_manager.check(reading.dose_rate)
            # Vardiya doz takibi
            await shift_manager.check(reading.cumulative_dose)
            # WebSocket push
            shift_info = await shift_manager.get_current()
            pending_info = await alarm_manager.get_pending_info()
            msg = {
                "type": "reading",
                "timestamp": reading.timestamp,
                "dose_rate": reading.dose_rate,
                "cumulative_dose": reading.cumulative_dose,
                "shift_name": shift_info["shift_name"],
                "shift_dose": shift_info["shift_dose"],
                "shift_active": shift_info["active"],
                "alarm_pending": pending_info["alarm_pending"],
                "alarm_pending_level": pending_info["alarm_pending_level"],
                "alarm_pending_elapsed": pending_info["alarm_pending_elapsed"],
                "alarm_pending_duration": pending_info["alarm_pending_duration"],
            }
            for client in list(app.state.ws_clients):
                try:
                    await client.send_json(msg)
                except Exception:
                    app.state.ws_clients.discard(client)
            # Remote log (fire-and-forget)
            asyncio.create_task(
                remote_log.forward_reading(
                    reading.timestamp, reading.dose_rate, reading.cumulative_dose, row_id
                )
            )

        reader.on_reading(on_reading)

        # Kalibrasyon faktörünü serial reader'a aktar
        cal_factor_str = await config.get("calibration_factor") or "1.0"
        reader.calibration_factor = float(cal_factor_str)

        # Background tasks
        interval = int(await config.get("sampling_interval") or "10")
        reader_task = asyncio.create_task(reader.run(interval=interval))
        sync_task = asyncio.create_task(remote_log.run_sync_loop(interval=60))
        wifi_task = asyncio.create_task(wifi.auto_connect_loop(config, alarm_manager))

        logger.info("mssRadMon başlatıldı — interval=%ds", interval)
        yield

        # Shutdown
        reader.stop()
        reader_task.cancel()
        sync_task.cancel()
        wifi_task.cancel()
        alarm_manager.shutdown()
        await db.close()
        logger.info("mssRadMon kapatıldı")

    app = FastAPI(title="mssRadMon", lifespan=lifespan)

    # Static dosyalar varsa mount et
    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    app.include_router(api.router)
    app.include_router(ws.router)
    app.include_router(admin.router)

    templates = Jinja2Templates(directory=TEMPLATE_DIR)
    from app.__version__ import __version__
    templates.env.globals["APP_VERSION"] = __version__

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard_page(request: Request):
        return templates.TemplateResponse("dashboard.html", {"request": request, "active": "dashboard"})

    @app.get("/admin/login", response_class=HTMLResponse, include_in_schema=False)
    async def admin_login_page(request: Request, error: int = 0):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": bool(error)}
        )

    @app.post("/admin/login", include_in_schema=False)
    async def admin_login(request: Request):
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        db = request.app.state.db
        pw_hash = _hash_password(password, username)
        row = await db.fetch_one(
            "SELECT username FROM users WHERE username = ? AND password_hash = ?",
            (username, pw_hash),
        )
        if row:
            token = _sign_cookie(username)
            resp = RedirectResponse(url="/admin", status_code=303)
            resp.set_cookie(
                COOKIE_NAME, token,
                max_age=_SESSION_TTL,
                httponly=True,
                samesite="lax",
            )
            return resp
        return RedirectResponse(url="/admin/login?error=1", status_code=303)

    @app.post("/admin/logout", include_in_schema=False)
    async def admin_logout(request: Request):
        resp = RedirectResponse(url="/admin/login", status_code=303)
        resp.delete_cookie(COOKIE_NAME, httponly=True, samesite="lax")
        return resp

    @app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    async def admin_page(request: Request):
        token = request.cookies.get(COOKIE_NAME, "")
        username = _verify_cookie(token)
        if not username:
            return RedirectResponse(url="/admin/login", status_code=303)
        row = await request.app.state.db.fetch_one(
            "SELECT role FROM users WHERE username = ?", (username,)
        )
        user_role = row["role"] if row else "viewer"
        return templates.TemplateResponse(
            "admin.html",
            {"request": request, "active": "admin", "user_role": user_role, "username": username},
        )

    @app.post("/api/apikey/generate", include_in_schema=False)
    async def generate_api_key(
        request: Request,
        _user: dict = Depends(require_admin),
    ):
        """Yeni API key üret ve kaydet. Admin cookie zorunlu."""
        new_key = secrets.token_hex(32)
        await request.app.state.config.set("api_key", new_key)
        return {"api_key": new_key}

    @app.get("/api/ssl/status", include_in_schema=False)
    async def ssl_status(
        request: Request,
        _user: dict = Depends(require_admin),
    ):
        return await request.app.state.ssl_manager.get_status()

    @app.post("/api/ssl/trust-ca", include_in_schema=False)
    async def ssl_trust_ca(
        request: Request,
        file: UploadFile = File(...),
        _user: dict = Depends(require_admin),
    ):
        pem_data = (await file.read()).decode("utf-8", errors="replace")
        return await request.app.state.ssl_manager.trust_ca(pem_data)

    @app.post("/api/ssl/request", include_in_schema=False)
    async def ssl_request_cert(
        request: Request,
        body: dict,
        _user: dict = Depends(require_admin),
    ):
        hostname = body.get("hostname", "").strip()
        if not hostname:
            raise HTTPException(400, detail="hostname zorunlu")
        return await request.app.state.ssl_manager.request_cert(hostname)

    @app.get("/api/users/me", include_in_schema=False)
    async def get_current_user_info(
        current_user: dict = Depends(get_current_user),
    ):
        return {"username": current_user["username"], "role": current_user["role"]}

    @app.get("/api/users", include_in_schema=False)
    async def list_users(
        request: Request,
        _user: dict = Depends(require_admin),
    ):
        rows = await request.app.state.db.fetch_all(
            "SELECT id, username, role FROM users ORDER BY id"
        )
        return rows

    @app.post("/api/users", include_in_schema=False)
    async def create_user(
        request: Request,
        body: dict,
        _user: dict = Depends(require_admin),
    ):
        username = body.get("username", "").strip()
        password = body.get("password", "")
        role = body.get("role", "viewer")
        if not username or not password:
            raise HTTPException(400, detail="username ve password zorunlu")
        if role not in ("admin", "viewer"):
            raise HTTPException(400, detail="role 'admin' veya 'viewer' olmalı")
        pw_hash = _hash_password(password, username)
        try:
            await request.app.state.db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, pw_hash, role),
            )
        except aiosqlite.IntegrityError:
            raise HTTPException(409, detail="Bu kullanıcı adı zaten mevcut")
        return {"ok": True}

    @app.delete("/api/users/{username}", include_in_schema=False)
    async def delete_user(
        request: Request,
        username: str,
        current_user: dict = Depends(require_admin),
    ):
        if username == current_user["username"]:
            raise HTTPException(400, detail="Kendi hesabınızı silemezsiniz")
        target = await request.app.state.db.fetch_one(
            "SELECT role FROM users WHERE username = ?", (username,)
        )
        if not target:
            raise HTTPException(404, detail="Kullanıcı bulunamadı")
        if target["role"] == "admin":
            count = await request.app.state.db.fetch_one(
                "SELECT COUNT(*) as n FROM users WHERE role = 'admin'"
            )
            if count["n"] <= 1:
                raise HTTPException(400, detail="Son admin silinemez")
        await request.app.state.db.execute(
            "DELETE FROM users WHERE username = ?", (username,)
        )
        return {"ok": True}

    @app.put("/api/users/{username}/password", include_in_schema=False)
    async def change_password(
        request: Request,
        username: str,
        body: dict,
        current_user: dict = Depends(get_current_user),
    ):
        is_self = username == current_user["username"]
        is_admin = current_user["role"] == "admin"
        if not is_self and not is_admin:
            raise HTTPException(403, detail="Başkasının şifresini değiştiremezsiniz")
        new_password = body.get("new_password", "")
        if not new_password:
            raise HTTPException(400, detail="new_password zorunlu")
        if is_self:
            current_password = body.get("current_password", "")
            if not current_password:
                raise HTTPException(400, detail="current_password zorunlu")
            row = await request.app.state.db.fetch_one(
                "SELECT id FROM users WHERE username = ? AND password_hash = ?",
                (username, _hash_password(current_password, username)),
            )
            if not row:
                raise HTTPException(400, detail="Mevcut şifre yanlış")
        new_hash = _hash_password(new_password, username)
        await request.app.state.db.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (new_hash, username),
        )
        return {"ok": True}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8090, reload=False)
