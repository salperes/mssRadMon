"""REST API endpointleri."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, Depends

from app.__version__ import __version__
from app.auth import verify_api_key

router = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(verify_api_key)])

TZ_TR = timezone(timedelta(hours=3))

DURATION_MAP = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def _period_start_iso(now_local: datetime, period: str) -> str:
    """Periyot başlangıcını UTC ISO string olarak hesapla (UTC+3 yerel saat baz alınır)."""
    if period == "day":
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "quarter":
        q_month = ((now_local.month - 1) // 3) * 3 + 1
        start_local = now_local.replace(month=q_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "half_year":
        h_month = 1 if now_local.month <= 6 else 7
        start_local = now_local.replace(month=h_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # year
        start_local = now_local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(timezone.utc).isoformat()


async def _calc_period_dose(db, since_iso: str) -> float:
    """Verilen UTC ISO tarihinden itibaren kümülatif doz farkını hesapla."""
    first = await db.fetch_one(
        "SELECT cumulative_dose FROM readings WHERE timestamp >= ? ORDER BY timestamp ASC LIMIT 1",
        (since_iso,),
    )
    last = await db.fetch_one(
        "SELECT cumulative_dose FROM readings WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 1",
        (since_iso,),
    )
    if first and last:
        return round(last["cumulative_dose"] - first["cumulative_dose"], 4)
    return 0.0


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
    """Bugünkü toplam kümülatif doz farkını döndür (UTC+3 gece yarısından itibaren)."""
    db = request.app.state.db
    now_local = datetime.now(TZ_TR)
    today_start = _period_start_iso(now_local, "day")
    daily = await _calc_period_dose(db, today_start)
    return {"date": now_local.strftime("%Y-%m-%d"), "daily_dose": daily}


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


@router.get("/period-doses")
async def get_period_doses(request: Request):
    """Günlük, aylık, 3 aylık, 6 aylık ve yıllık kümülatif doz özetleri (UTC+3)."""
    db = request.app.state.db
    now_local = datetime.now(TZ_TR)
    periods = {
        "daily": "day",
        "monthly": "month",
        "quarterly": "quarter",
        "half_yearly": "half_year",
        "yearly": "year",
    }
    result = {}
    for key, period in periods.items():
        since = _period_start_iso(now_local, period)
        result[key] = await _calc_period_dose(db, since)
    return result


@router.get("/device")
async def get_device(request: Request):
    """Cihaz kimlik bilgilerini döndür."""
    config = request.app.state.config
    return {
        "device_name": await config.get("device_name") or "",
        "device_location": await config.get("device_location") or "",
        "device_serial": await config.get("device_serial") or "",
    }
