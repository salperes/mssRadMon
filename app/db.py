"""SQLite veritabani yonetimi."""
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    dose_rate REAL NOT NULL,
    cumulative_dose REAL NOT NULL,
    remote_synced INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_readings_sync ON readings(remote_synced) WHERE remote_synced = 0;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alarm_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    dose_rate REAL NOT NULL,
    action_taken TEXT NOT NULL,
    remote_synced INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alarm_ts ON alarm_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_alarm_sync ON alarm_log(remote_synced) WHERE remote_synced = 0;

CREATE TABLE IF NOT EXISTS shift_doses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id TEXT NOT NULL,
    shift_name TEXT NOT NULL,
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    dose REAL NOT NULL DEFAULT 0.0,
    completed INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_shift_doses_date ON shift_doses(date);
CREATE INDEX IF NOT EXISTS idx_shift_doses_active ON shift_doses(completed) WHERE completed = 0;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'viewer'))
);
"""


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def init(self):
        """Baglantiyi ac ve semayi olustur."""
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def execute(self, sql: str, params: tuple = ()) -> int:
        """Tek bir SQL calistir, lastrowid dondur."""
        cursor = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cursor.lastrowid

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """Tum sonuclari dict listesi olarak dondur."""
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        """Tek bir sonuc dondur, yoksa None."""
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None
