"""mssRadMon — FastAPI uygulama giriş noktası."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.alarm import AlarmManager
from app.config import Config
from app.db import Database
from app.remote_log import RemoteLogForwarder
from app.routers import admin, api, ws
from app.serial_reader import GammaScoutReader, Reading
from app.shift import ShiftManager
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
            msg = {
                "type": "reading",
                "timestamp": reading.timestamp,
                "dose_rate": reading.dose_rate,
                "cumulative_dose": reading.cumulative_dose,
                "shift_name": shift_info["shift_name"],
                "shift_dose": shift_info["shift_dose"],
                "shift_active": shift_info["active"],
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

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard_page(request: Request):
        return templates.TemplateResponse("dashboard.html", {"request": request, "active": "dashboard"})

    @app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    async def admin_page(request: Request):
        return templates.TemplateResponse("admin.html", {"request": request, "active": "admin"})

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8090, reload=False)
