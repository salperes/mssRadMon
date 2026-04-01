"""REST API endpointleri."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request

from app.__version__ import __version__

router = APIRouter(prefix="/api", tags=["api"])

DURATION_MAP = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


@router.get("/current")
async def get_current(request: Request):
    """Son ölçüm verisini döndür."""
    db = request.app.state.db
    row = await db.fetch_one(
        "SELECT timestamp, dose_rate, cumulative_dose FROM readings ORDER BY id DESC LIMIT 1"
    )
    connected = request.app.state.reader.connected
    alarm = request.app.state.alarm
    pending = await alarm.get_pending_info()
    if row:
        return {
            "timestamp": row["timestamp"],
            "dose_rate": row["dose_rate"],
            "cumulative_dose": row["cumulative_dose"],
            "connected": connected,
            **pending,
        }
    return {"timestamp": None, "dose_rate": None, "cumulative_dose": None, "connected": connected, **pending}


@router.get("/readings")
async def get_readings(request: Request, last: str = "1h"):
    """Belirli zaman aralığındaki okumaları döndür."""
    db = request.app.state.db
    delta = DURATION_MAP.get(last, timedelta(hours=1))
    since = (datetime.now(timezone.utc) - delta).isoformat()
    rows = await db.fetch_all(
        "SELECT timestamp, dose_rate, cumulative_dose FROM readings WHERE timestamp >= ? ORDER BY timestamp",
        (since,),
    )
    return rows


@router.get("/daily-dose")
async def get_daily_dose(request: Request):
    """Bugünkü toplam kümülatif doz farkını döndür."""
    db = request.app.state.db
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    first = await db.fetch_one(
        "SELECT cumulative_dose FROM readings WHERE timestamp >= ? ORDER BY timestamp ASC LIMIT 1",
        (today_start,),
    )
    last = await db.fetch_one(
        "SELECT cumulative_dose FROM readings WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 1",
        (today_start,),
    )

    if first and last:
        daily = last["cumulative_dose"] - first["cumulative_dose"]
    else:
        daily = 0.0

    return {"date": today_start[:10], "daily_dose": daily}


@router.get("/health")
async def get_health():
    """Uygulama sağlık ve versiyon bilgisi."""
    return {"status": "ok", "version": __version__}


@router.get("/status")
async def get_status(request: Request):
    """Cihaz ve uygulama durumunu döndür."""
    reader = request.app.state.reader
    return {
        "connected": reader.connected,
        "port": reader.port,
        "version": __version__,
    }


@router.get("/alarms")
async def get_alarms(request: Request, last: str = "24h"):
    """Alarm geçmişini döndür."""
    db = request.app.state.db
    delta = DURATION_MAP.get(last, timedelta(hours=24))
    since = (datetime.now(timezone.utc) - delta).isoformat()
    rows = await db.fetch_all(
        "SELECT timestamp, level, dose_rate, action_taken FROM alarm_log WHERE timestamp >= ? ORDER BY timestamp DESC",
        (since,),
    )
    return rows


@router.get("/shift/current")
async def get_shift_current(request: Request):
    """Aktif vardiya ve anlik doz."""
    shift_manager = request.app.state.shift_manager
    return await shift_manager.get_current()


@router.get("/shift/history")
async def get_shift_history(request: Request, days: int = 7):
    """Gecmis vardiya dozlari."""
    shift_manager = request.app.state.shift_manager
    return await shift_manager.get_history(days=days)
