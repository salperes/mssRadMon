"""Vardiya yonetimi — aktif vardiya tespiti ve doz takibi."""
import json
import logging
from datetime import datetime, timedelta

from app.config import Config
from app.db import Database

logger = logging.getLogger(__name__)


class ShiftManager:
    def __init__(self, db: Database, config: Config):
        self._db = db
        self._config = config
        self._last_cumulative: float | None = None
        self._active_shift_id: str | None = None
        self._active_shift_date: str | None = None

    async def _get_shifts(self) -> list[dict]:
        """Config'den vardiya tanimlarini oku."""
        raw = await self._config.get("shifts")
        if not raw:
            return []
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return []

    def _find_active_shift(self, shifts: list[dict], now: datetime) -> dict | None:
        """Su anki saat ve gune uyan vardiyayi bul."""
        current_time = now.strftime("%H:%M")
        weekday = now.isoweekday()  # 1=Mon, 7=Sun

        for shift in shifts:
            if weekday not in shift.get("days", []):
                continue
            start = shift["start"]
            end = shift["end"]
            if start < end:
                # Normal vardiya: 08:00-16:00
                if start <= current_time < end:
                    return shift
            elif start > end:
                # Gece vardiyasi: 22:00-06:00
                if current_time >= start or current_time < end:
                    return shift
        return None

    def _shift_date(self, active: dict, now: datetime) -> str:
        """Vardiya tarihini hesapla.

        Gece vardiyas (start > end) icin gece yarisi ile bitis saati arasindaki
        sure dunkun tarihine aittir; boylece tek kayit gece yarisi bolunmez.
        """
        start = active["start"]
        end = active["end"]
        current_time = now.strftime("%H:%M")
        if start > end and current_time < end:
            return (now - timedelta(days=1)).strftime("%Y-%m-%d")
        return now.strftime("%Y-%m-%d")

    async def check(self, cumulative_dose: float):
        """Her okumada cagrilir. Aktif vardiyayi belirler, dozu gunceller."""
        now = datetime.now()
        shifts = await self._get_shifts()

        if not shifts:
            self._last_cumulative = cumulative_dose
            self._active_shift_id = None
            self._active_shift_date = None
            return

        active = self._find_active_shift(shifts, now)

        # Onceki aktif vardiya bittiyse kapat
        if self._active_shift_id and (active is None or active["id"] != self._active_shift_id):
            await self._db.execute(
                "UPDATE shift_doses SET completed = 1 WHERE shift_id = ? AND date = ? AND completed = 0",
                (self._active_shift_id, self._active_shift_date),
            )
            self._active_shift_id = None
            self._active_shift_date = None

        if active is None:
            self._last_cumulative = cumulative_dose
            return

        self._active_shift_id = active["id"]
        today = self._shift_date(active, now)
        self._active_shift_date = today

        # Bu vardiya icin bugunun kaydini bul veya olustur
        row = await self._db.fetch_one(
            "SELECT id, dose FROM shift_doses WHERE shift_id = ? AND date = ? AND completed = 0",
            (active["id"], today),
        )

        if row is None:
            # completed=1 olan kayit var mi? (servis restart sonrasi)
            existing = await self._db.fetch_one(
                "SELECT id, dose FROM shift_doses WHERE shift_id = ? AND date = ?",
                (active["id"], today),
            )
            if existing:
                # Mevcut kaydi tekrar ac
                await self._db.execute(
                    "UPDATE shift_doses SET completed = 0 WHERE id = ?",
                    (existing["id"],),
                )
                row = existing
            else:
                # Yeni vardiya basladi
                await self._db.execute(
                    "INSERT INTO shift_doses (shift_id, shift_name, date, start_time, end_time, dose, completed) VALUES (?, ?, ?, ?, ?, 0.0, 0)",
                    (active["id"], active["name"], today, active["start"], active["end"]),
                )
                self._last_cumulative = cumulative_dose
                return

        # Doz farkini hesapla ve ekle
        if self._last_cumulative is not None:
            delta = cumulative_dose - self._last_cumulative
            if delta > 0:
                new_dose = row["dose"] + delta
                await self._db.execute(
                    "UPDATE shift_doses SET dose = ? WHERE id = ?",
                    (new_dose, row["id"]),
                )

        self._last_cumulative = cumulative_dose

    async def get_current(self) -> dict:
        """Aktif vardiya adi + anlik vardiya dozunu dondur."""
        now = datetime.now()
        shifts = await self._get_shifts()
        active = self._find_active_shift(shifts, now)

        if active is None:
            return {"active": False, "shift_name": None, "shift_dose": 0.0}

        today = self._shift_date(active, now)
        row = await self._db.fetch_one(
            "SELECT dose FROM shift_doses WHERE shift_id = ? AND date = ? AND completed = 0",
            (active["id"], today),
        )
        return {
            "active": True,
            "shift_name": active["name"],
            "shift_dose": row["dose"] if row else 0.0,
        }

    async def get_history(self, days: int = 7) -> list[dict]:
        """Son N gunun tamamlanmis vardiya dozlarini dondur."""
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = await self._db.fetch_all(
            "SELECT shift_name, date, start_time, end_time, dose FROM shift_doses WHERE date >= ? ORDER BY date DESC, start_time DESC",
            (since,),
        )
        return rows

    async def close_stale(self):
        """Uygulama baslarken completed=0 olan eski kayitlari kapat.

        Aktif bir gece vardiyasi varsa (gece yarisi - bitis saati arasinda),
        o vardiyaya ait dunku kaydi henuz aktif oldugu icin kapatilmaz.
        """
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        shifts = await self._get_shifts()
        active = self._find_active_shift(shifts, now)
        is_overnight_morning = (
            active is not None
            and active["start"] > active["end"]
            and now.strftime("%H:%M") < active["end"]
        )

        if is_overnight_morning:
            # Dunkunden oncesini kapat; dunku aktif gece vardiyasini dokunma
            await self._db.execute(
                "UPDATE shift_doses SET completed = 1 WHERE completed = 0 AND date < ? AND NOT (shift_id = ? AND date = ?)",
                (today, active["id"], yesterday),
            )
        else:
            await self._db.execute(
                "UPDATE shift_doses SET completed = 1 WHERE completed = 0 AND date < ?",
                (today,),
            )
