# mssRadMon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a radiation monitoring system that reads GammaScout Online data via USB serial, stores it in SQLite, displays it on a web dashboard with live updates, and provides configurable alarms and remote log forwarding.

**Architecture:** Single Python asyncio process running FastAPI (HTTP + WebSocket), a serial reader loop, alarm manager with GPIO output, and async remote log forwarder. All components share the same event loop. SQLite for persistence.

**Tech Stack:** Python 3.13, FastAPI, uvicorn, pyserial, aiohttp (for remote log HTTP client), gpiozero, aiosqlite, Jinja2, Chart.js

**Spec:** `docs/superpowers/specs/2026-03-31-mssradmon-design.md`

---

## File Structure

```
mssRadMon/
├── app/
│   ├── __init__.py              # Package marker
│   ├── main.py                  # FastAPI app, lifespan startup/shutdown, asyncio tasks
│   ├── config.py                # Read/write settings from DB, defaults dict
│   ├── db.py                    # SQLite connection, schema creation, query helpers
│   ├── serial_reader.py         # GammaScout serial protocol, asyncio read loop
│   ├── alarm.py                 # Alarm state machine, GPIO control, email sender
│   ├── remote_log.py            # HTTP POST forwarder, sync queue processor
│   ├── routers/
│   │   ├── __init__.py          # Package marker
│   │   ├── api.py               # GET /api/current, /api/readings, /api/daily-dose, /api/status, /api/alarms
│   │   ├── ws.py                # WebSocket /ws/live endpoint, client registry
│   │   └── admin.py             # GET/PUT /api/settings
│   ├── templates/
│   │   ├── base.html            # Shared layout (head, nav, footer)
│   │   ├── dashboard.html       # Live dose rate, chart, daily dose, status
│   │   └── admin.html           # Settings forms, alarm history table
│   └── static/
│       ├── css/
│       │   └── style.css        # All styles
│       ├── js/
│       │   ├── dashboard.js     # WebSocket client, Chart.js setup, DOM updates
│       │   └── admin.js         # Settings form handler, alarm history loader
│       └── lib/
│           └── chart.js         # Chart.js library (local copy)
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures (test DB, mock serial, test client)
│   ├── test_db.py               # DB schema, CRUD operations
│   ├── test_config.py           # Settings read/write, defaults
│   ├── test_serial_reader.py    # Protocol parsing, reconnect logic
│   ├── test_alarm.py            # Threshold checks, state machine, GPIO mock
│   ├── test_remote_log.py       # Sync queue, retry logic
│   ├── test_api.py              # REST endpoint responses
│   ├── test_ws.py               # WebSocket message flow
│   └── test_admin.py            # Settings API endpoints
├── data/                        # Runtime: readings.db (gitignored)
├── docs/
│   ├── serial_protocol.md       # GammaScout protocol documentation (Task 1 output)
│   └── superpowers/
│       ├── specs/
│       │   └── 2026-03-31-mssradmon-design.md
│       └── plans/
│           └── 2026-03-31-mssradmon-implementation.md
├── systemd/
│   └── mssradmon.service        # systemd unit file
├── requirements.txt             # Production dependencies
├── requirements-dev.txt         # Test dependencies
├── .gitignore
└── README.md
```

---

## Task 1: Serial Protokol Keşfi ve Dokümantasyonu

**Goal:** GammaScout Online cihazıyla gerçek serial iletişim kurup protokol parametrelerini (baud rate, data format, komutlar, yanıt formatı) doğrulamak ve dokümante etmek. Bu task'ın çıktısı diğer tüm task'ların serial haberleşme kısmına temel oluşturur.

**Files:**
- Create: `docs/serial_protocol.md`
- Create: `tools/serial_probe.py` (tek seferlik keşif scripti)

**Not:** Bu task interaktif — cihaz yanıtlarına göre adımlar adapte edilecek. Aşağıdaki adımlar beklenen protokole dayanır, gerçek cihaz farklı davranırsa güncellenmelidir.

- [ ] **Step 1: pyserial kur**

```bash
pip3 install pyserial
```

- [ ] **Step 2: Keşif scripti oluştur**

```python
#!/usr/bin/env python3
"""GammaScout Online serial protocol probe tool."""
import serial
import time
import sys

PORT = "/dev/ttyUSB0"

# Denenecek baud rate'ler (en olası ilk)
BAUD_RATES = [9600, 2400, 1200, 19200]

# Denenecek serial config'ler
CONFIGS = [
    {"bytesize": serial.SEVENBITS, "parity": serial.PARITY_EVEN, "stopbits": serial.STOPBITS_ONE},
    {"bytesize": serial.EIGHTBITS, "parity": serial.PARITY_NONE, "stopbits": serial.STOPBITS_ONE},
]


def try_config(baud, config):
    """Verilen config ile bağlanıp veri okumayı dene."""
    label = f"baud={baud} bits={config['bytesize']} parity={config['parity']} stop={config['stopbits']}"
    print(f"\n--- Deneniyor: {label} ---")
    try:
        ser = serial.Serial(
            port=PORT,
            baudrate=baud,
            bytesize=config["bytesize"],
            parity=config["parity"],
            stopbits=config["stopbits"],
            timeout=2,
        )
        time.sleep(0.5)

        # Önce PC moduna geçmeyi dene
        ser.write(b"P")
        time.sleep(1)

        # Yanıt oku
        data = ser.read(256)
        if data:
            print(f"  Yanıt ({len(data)} byte): {data}")
            print(f"  Hex: {data.hex(' ')}")
            try:
                print(f"  ASCII: {data.decode('ascii', errors='replace')}")
            except Exception:
                pass

        # Birkaç saniye daha dinle
        for i in range(5):
            time.sleep(1)
            data = ser.read(256)
            if data:
                print(f"  +{i+1}s ({len(data)} byte): {data}")
                print(f"  Hex: {data.hex(' ')}")
                try:
                    print(f"  ASCII: {data.decode('ascii', errors='replace')}")
                except Exception:
                    pass

        # PC modundan çık
        ser.write(b"X")
        time.sleep(0.5)
        leftover = ser.read(256)
        if leftover:
            print(f"  X sonrası: {leftover}")

        ser.close()
        return True
    except serial.SerialException as e:
        print(f"  HATA: {e}")
        return False


def main():
    print(f"GammaScout Serial Protocol Probe")
    print(f"Port: {PORT}")
    print(f"=" * 50)

    for baud in BAUD_RATES:
        for config in CONFIGS:
            try_config(baud, config)
            time.sleep(1)

    # Versiyon sorgusu dene (bazı GammaScout modelleri 'v' komutunu destekler)
    print(f"\n--- Versiyon sorgusu ---")
    try:
        ser = serial.Serial(PORT, 9600, bytesize=serial.SEVENBITS,
                            parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_ONE, timeout=2)
        for cmd in [b"v", b"V", b"P", b"z", b"b"]:
            ser.write(cmd)
            time.sleep(1)
            data = ser.read(256)
            print(f"  Komut '{cmd.decode()}': {data.hex(' ') if data else '(yanıt yok)'}")
            if data:
                try:
                    print(f"    ASCII: {data.decode('ascii', errors='replace')}")
                except Exception:
                    pass
        ser.close()
    except Exception as e:
        print(f"  HATA: {e}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Scripti çalıştır, çıktıları kaydet**

```bash
cd /home/alper/mssRadMon
python3 tools/serial_probe.py 2>&1 | tee docs/serial_probe_output.txt
```

Çıktıyı analiz et: hangi baud rate ve config yanıt verdi, yanıt formatı nedir.

- [ ] **Step 4: PC Mode veri formatını analiz et**

Probe çıktısına göre, çalışan config ile daha detaylı veri okuma yap. Birkaç dakika sürekli veri oku ve formatı çöz:

```python
#!/usr/bin/env python3
"""GammaScout PC mode continuous read - parametreleri probe çıktısına göre güncelle."""
import serial
import time

# Bu değerleri Step 3 sonucuna göre güncelle
PORT = "/dev/ttyUSB0"
BAUD = 9600
BYTESIZE = serial.SEVENBITS
PARITY = serial.PARITY_EVEN
STOPBITS = serial.STOPBITS_ONE

ser = serial.Serial(PORT, BAUD, bytesize=BYTESIZE, parity=PARITY,
                    stopbits=STOPBITS, timeout=2)
time.sleep(0.5)

print("PC moduna geçiliyor...")
ser.write(b"P")
time.sleep(1)

try:
    for i in range(60):  # 60 okuma
        data = ser.read(256)
        if data:
            print(f"[{i:3d}] ({len(data):3d}B) hex={data.hex(' ')}")
            try:
                print(f"      ascii={data.decode('ascii', errors='replace').strip()}")
            except Exception:
                pass
        time.sleep(1)
finally:
    print("PC modundan çıkılıyor...")
    ser.write(b"X")
    time.sleep(0.5)
    ser.close()
```

- [ ] **Step 5: Protokol dokümanını yaz**

Probe ve analiz sonuçlarına dayanarak `docs/serial_protocol.md` dosyasını oluştur. İçerik:

```markdown
# GammaScout Online Serial Protokolü

## Bağlantı Parametreleri

| Parametre | Değer |
|-----------|-------|
| Port | /dev/ttyUSB0 |
| Baud Rate | (probe çıktısından) |
| Data Bits | (probe çıktısından) |
| Parity | (probe çıktısından) |
| Stop Bits | (probe çıktısından) |

## Komutlar

| Komut | Açıklama | Yanıt |
|-------|----------|-------|
| P | PC Mode giriş | (gözlemlenen yanıt) |
| X | PC Mode çıkış | (gözlemlenen yanıt) |
| v | Versiyon sorgusu | (gözlemlenen yanıt) |

## PC Mode Veri Formatı

(Gözlemlenen format — byte pozisyonları, alan açıklamaları, örnek parse)

## Örnek Veri

(Ham hex + parse edilmiş değerler)

## Notlar

(Keşif sırasında öğrenilen ek bilgiler)
```

- [ ] **Step 6: Commit**

```bash
git add docs/serial_protocol.md tools/serial_probe.py
git commit -m "docs: GammaScout serial protokol keşfi ve dokümantasyonu"
```

---

## Task 2: Proje İskeleti ve Bağımlılıklar

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `app/__init__.py`
- Create: `app/routers/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: `.gitignore` oluştur**

```gitignore
__pycache__/
*.pyc
*.pyo
.venv/
venv/
data/
*.db
.env
*.egg-info/
dist/
build/
.pytest_cache/
docs/serial_probe_output.txt
tools/
```

- [ ] **Step 2: `requirements.txt` oluştur**

```
fastapi==0.115.*
uvicorn[standard]==0.34.*
pyserial==3.5.*
aiosqlite==0.21.*
aiohttp==3.11.*
gpiozero==2.0.*
jinja2==3.1.*
```

- [ ] **Step 3: `requirements-dev.txt` oluştur**

```
-r requirements.txt
pytest==8.3.*
pytest-asyncio==0.25.*
httpx==0.28.*
```

- [ ] **Step 4: Bağımlılıkları kur**

```bash
cd /home/alper/mssRadMon
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

- [ ] **Step 5: Paket dosyaları oluştur**

`app/__init__.py`:
```python
```

`app/routers/__init__.py`:
```python
```

`tests/__init__.py`:
```python
```

- [ ] **Step 6: Test conftest oluştur**

`tests/conftest.py`:
```python
import asyncio
import os
import tempfile
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_db_path():
    """Her test için geçici SQLite DB dosyası."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    os.unlink(path)


@pytest_asyncio.fixture
async def test_client(test_db_path):
    """FastAPI test client. DB path'i override eder."""
    os.environ["MSSRADMON_DB_PATH"] = test_db_path
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    os.environ.pop("MSSRADMON_DB_PATH", None)
```

- [ ] **Step 7: Testlerin çalıştığını doğrula**

```bash
cd /home/alper/mssRadMon
source .venv/bin/activate
python -m pytest tests/ -v
```

Expected: "no tests ran" — hata yok.

- [ ] **Step 8: Commit**

```bash
git add .gitignore requirements.txt requirements-dev.txt app/__init__.py app/routers/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: proje iskeleti, bağımlılıklar ve test altyapısı"
```

---

## Task 3: Veritabanı Katmanı (db.py + config.py)

**Files:**
- Create: `app/db.py`
- Create: `app/config.py`
- Create: `tests/test_db.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: DB testlerini yaz**

`tests/test_db.py`:
```python
import pytest
import pytest_asyncio

from app.db import Database


@pytest_asyncio.fixture
async def db(test_db_path):
    database = Database(test_db_path)
    await database.init()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_tables_created(db):
    """init() readings, settings, alarm_log tablolarını oluşturmalı."""
    tables = await db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = [row["name"] for row in tables]
    assert "alarm_log" in names
    assert "readings" in names
    assert "settings" in names


@pytest.mark.asyncio
async def test_insert_reading(db):
    """Ölçüm verisi eklenebilmeli."""
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-03-31T12:00:00Z", 0.12, 45.6),
    )
    rows = await db.fetch_all("SELECT * FROM readings")
    assert len(rows) == 1
    assert rows[0]["dose_rate"] == 0.12
    assert rows[0]["cumulative_dose"] == 45.6
    assert rows[0]["remote_synced"] == 0


@pytest.mark.asyncio
async def test_insert_alarm(db):
    """Alarm kaydı eklenebilmeli."""
    await db.execute(
        "INSERT INTO alarm_log (timestamp, level, dose_rate, action_taken) VALUES (?, ?, ?, ?)",
        ("2026-03-31T12:00:00Z", "high", 0.55, "buzzer,light"),
    )
    rows = await db.fetch_all("SELECT * FROM alarm_log")
    assert len(rows) == 1
    assert rows[0]["level"] == "high"


@pytest.mark.asyncio
async def test_readings_by_time_range(db):
    """Zaman aralığına göre okuma sorgusu."""
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-03-31T10:00:00Z", 0.10, 10.0),
    )
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-03-31T12:00:00Z", 0.12, 20.0),
    )
    rows = await db.fetch_all(
        "SELECT * FROM readings WHERE timestamp >= ? ORDER BY timestamp",
        ("2026-03-31T11:00:00Z",),
    )
    assert len(rows) == 1
    assert rows[0]["dose_rate"] == 0.12
```

- [ ] **Step 2: Testlerin fail ettiğini doğrula**

```bash
python -m pytest tests/test_db.py -v
```

Expected: FAIL — `app.db` modülü yok.

- [ ] **Step 3: `app/db.py` implementasyonu**

```python
"""SQLite veritabanı yönetimi."""
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
"""


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def init(self):
        """Bağlantıyı aç ve şemayı oluştur."""
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def execute(self, sql: str, params: tuple = ()) -> int:
        """Tek bir SQL çalıştır, lastrowid döndür."""
        cursor = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cursor.lastrowid

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """Tüm sonuçları dict listesi olarak döndür."""
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        """Tek bir sonuç döndür, yoksa None."""
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None
```

- [ ] **Step 4: DB testlerinin geçtiğini doğrula**

```bash
python -m pytest tests/test_db.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Config testlerini yaz**

`tests/test_config.py`:
```python
import pytest
import pytest_asyncio

from app.config import Config, DEFAULTS
from app.db import Database


@pytest_asyncio.fixture
async def config(test_db_path):
    db = Database(test_db_path)
    await db.init()
    cfg = Config(db)
    await cfg.init()
    yield cfg
    await db.close()


@pytest.mark.asyncio
async def test_defaults_loaded(config):
    """init() tüm varsayılan ayarları yüklemeli."""
    val = await config.get("sampling_interval")
    assert val == "10"


@pytest.mark.asyncio
async def test_get_nonexistent_returns_none(config):
    """Olmayan anahtar None döndürmeli."""
    val = await config.get("nonexistent_key")
    assert val is None


@pytest.mark.asyncio
async def test_set_and_get(config):
    """Ayar yazıp okuyabilmeli."""
    await config.set("threshold_high", "0.8")
    val = await config.get("threshold_high")
    assert val == "0.8"


@pytest.mark.asyncio
async def test_get_all(config):
    """Tüm ayarları dict olarak döndürmeli."""
    all_settings = await config.get_all()
    assert isinstance(all_settings, dict)
    assert all_settings["sampling_interval"] == "10"
    assert all_settings["threshold_high"] == "0.5"


@pytest.mark.asyncio
async def test_defaults_not_overwritten(config):
    """Mevcut ayar varsa init() üzerine yazmamalı."""
    await config.set("sampling_interval", "30")
    # Tekrar init() çağır
    await config.init()
    val = await config.get("sampling_interval")
    assert val == "30"
```

- [ ] **Step 6: Config testlerinin fail ettiğini doğrula**

```bash
python -m pytest tests/test_config.py -v
```

Expected: FAIL — `app.config` modülü yok.

- [ ] **Step 7: `app/config.py` implementasyonu**

```python
"""Uygulama ayarları yönetimi — SQLite settings tablosu üzerinden."""
from app.db import Database

DEFAULTS: dict[str, str] = {
    "sampling_interval": "10",
    "threshold_high": "0.5",
    "threshold_high_high": "1.0",
    "alarm_buzzer_enabled": "true",
    "alarm_email_enabled": "false",
    "alarm_email_to": "",
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_user": "",
    "smtp_pass": "",
    "remote_log_enabled": "false",
    "remote_log_url": "",
    "remote_log_api_key": "",
    "gpio_buzzer_pin": "17",
    "gpio_light_pin": "27",
    "gpio_emergency_pin": "22",
    "alarm_high_actions": "buzzer,light",
    "alarm_high_high_actions": "buzzer,light,emergency",
}


class Config:
    def __init__(self, db: Database):
        self._db = db

    async def init(self):
        """Eksik varsayılan ayarları DB'ye yaz. Mevcutların üzerine yazmaz."""
        for key, value in DEFAULTS.items():
            existing = await self._db.fetch_one(
                "SELECT value FROM settings WHERE key = ?", (key,)
            )
            if existing is None:
                await self._db.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)", (key, value)
                )

    async def get(self, key: str) -> str | None:
        """Tek bir ayar değerini döndür."""
        row = await self._db.fetch_one(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        return row["value"] if row else None

    async def set(self, key: str, value: str):
        """Ayar yaz (INSERT OR REPLACE)."""
        await self._db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )

    async def get_all(self) -> dict[str, str]:
        """Tüm ayarları dict olarak döndür."""
        rows = await self._db.fetch_all("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in rows}
```

- [ ] **Step 8: Tüm testlerin geçtiğini doğrula**

```bash
python -m pytest tests/test_db.py tests/test_config.py -v
```

Expected: 9 PASSED.

- [ ] **Step 9: Commit**

```bash
git add app/db.py app/config.py tests/test_db.py tests/test_config.py
git commit -m "feat: veritabanı katmanı ve ayar yönetimi (db.py, config.py)"
```

---

## Task 4: Serial Reader Modülü

**Files:**
- Create: `app/serial_reader.py`
- Create: `tests/test_serial_reader.py`

**Not:** Bu task, Task 1'deki protokol keşfi sonuçlarına bağlıdır. Aşağıdaki kod, beklenen protokolü temel alır — keşif sonuçlarına göre parse mantığı güncellenmelidir.

- [ ] **Step 1: Serial reader testlerini yaz**

`tests/test_serial_reader.py`:
```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.serial_reader import GammaScoutReader, Reading


@pytest.fixture
def mock_serial():
    """Mock serial port."""
    ser = MagicMock()
    ser.is_open = True
    ser.close = MagicMock()
    ser.write = MagicMock()
    ser.read = MagicMock(return_value=b"")
    ser.readline = MagicMock(return_value=b"")
    ser.in_waiting = 0
    return ser


def test_parse_reading_valid():
    """Geçerli cihaz çıktısını parse edebilmeli."""
    # Not: Bu test Task 1 sonrasında gerçek formata göre güncellenecek
    reader = GammaScoutReader.__new__(GammaScoutReader)
    # Örnek: "0.12 µSv/h  45.60 µSv" gibi bir format beklenebilir
    # Gerçek format Task 1'de belirlenecek
    raw = b"0.12 45.60\r\n"
    reading = reader.parse_reading(raw)
    assert reading is not None
    assert reading.dose_rate == 0.12
    assert reading.cumulative_dose == 45.60
    assert reading.timestamp is not None


def test_parse_reading_empty():
    """Boş veri None döndürmeli."""
    reader = GammaScoutReader.__new__(GammaScoutReader)
    reading = reader.parse_reading(b"")
    assert reading is None


def test_parse_reading_garbage():
    """Bozuk veri None döndürmeli."""
    reader = GammaScoutReader.__new__(GammaScoutReader)
    reading = reader.parse_reading(b"\xff\xfe\x00\x01")
    assert reading is None


def test_reading_dataclass():
    """Reading dataclass alanları doğru olmalı."""
    r = Reading(timestamp="2026-03-31T12:00:00Z", dose_rate=0.12, cumulative_dose=45.6)
    assert r.dose_rate == 0.12
    assert r.cumulative_dose == 45.6
```

- [ ] **Step 2: Testlerin fail ettiğini doğrula**

```bash
python -m pytest tests/test_serial_reader.py -v
```

Expected: FAIL — `app.serial_reader` modülü yok.

- [ ] **Step 3: `app/serial_reader.py` implementasyonu**

```python
"""GammaScout Online serial okuyucu."""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import serial

logger = logging.getLogger(__name__)


@dataclass
class Reading:
    timestamp: str
    dose_rate: float  # µSv/h
    cumulative_dose: float  # µSv


class GammaScoutReader:
    """GammaScout Online cihazından serial port üzerinden veri okur."""

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        bytesize: int = serial.SEVENBITS,
        parity: str = serial.PARITY_EVEN,
        stopbits: int = serial.STOPBITS_ONE,
    ):
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self._serial: serial.Serial | None = None
        self._running = False
        self._connected = False
        self._on_reading: Callable[[Reading], None] | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    def on_reading(self, callback: Callable[[Reading], None]):
        """Yeni okuma geldiğinde çağrılacak callback'i ata."""
        self._on_reading = callback

    def connect(self) -> bool:
        """Serial porta bağlan ve PC moduna geç."""
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=2,
            )
            # PC moduna geç
            self._serial.write(b"P")
            self._connected = True
            logger.info("GammaScout bağlantısı kuruldu: %s", self.port)
            return True
        except serial.SerialException as e:
            logger.error("Serial bağlantı hatası: %s", e)
            self._connected = False
            return False

    def disconnect(self):
        """PC modundan çık ve bağlantıyı kapat."""
        if self._serial and self._serial.is_open:
            try:
                self._serial.write(b"X")
                self._serial.close()
            except serial.SerialException:
                pass
        self._connected = False
        logger.info("GammaScout bağlantısı kapatıldı")

    def parse_reading(self, raw: bytes) -> Reading | None:
        """Ham serial verisini Reading'e parse et.

        NOT: Bu method Task 1 protokol keşfi sonrasında gerçek formata
        göre güncellenecektir. Şu anki implementasyon placeholder format
        kullanır: "dose_rate cumulative_dose\\r\\n"
        """
        if not raw or len(raw.strip()) == 0:
            return None
        try:
            text = raw.decode("ascii", errors="ignore").strip()
            if not text:
                return None
            parts = text.split()
            if len(parts) < 2:
                return None
            dose_rate = float(parts[0])
            cumulative_dose = float(parts[1])
            timestamp = datetime.now(timezone.utc).isoformat()
            return Reading(
                timestamp=timestamp,
                dose_rate=dose_rate,
                cumulative_dose=cumulative_dose,
            )
        except (ValueError, IndexError, UnicodeDecodeError):
            logger.warning("Parse hatası: %s", raw.hex(" ") if raw else "empty")
            return None

    def read_once(self) -> Reading | None:
        """Serial porttan tek bir okuma yap."""
        if not self._serial or not self._serial.is_open:
            return None
        try:
            raw = self._serial.readline()
            return self.parse_reading(raw)
        except serial.SerialException as e:
            logger.error("Okuma hatası: %s", e)
            self._connected = False
            return None

    async def run(self, interval: int = 10):
        """Ana okuma döngüsü. interval saniyede bir okuma yapar."""
        self._running = True
        while self._running:
            if not self._connected:
                logger.info("Yeniden bağlanılıyor...")
                if not self.connect():
                    await asyncio.sleep(5)
                    continue

            loop = asyncio.get_event_loop()
            reading = await loop.run_in_executor(None, self.read_once)

            if reading and self._on_reading:
                await self._on_reading(reading)
            elif reading is None and not self._connected:
                # Bağlantı kopmuş, reconnect denenecek
                self.disconnect()
                await asyncio.sleep(5)
                continue

            await asyncio.sleep(interval)

    def stop(self):
        """Okuma döngüsünü durdur."""
        self._running = False
        self.disconnect()
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

```bash
python -m pytest tests/test_serial_reader.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/serial_reader.py tests/test_serial_reader.py
git commit -m "feat: GammaScout serial reader modülü"
```

---

## Task 5: Alarm Sistemi (alarm.py)

**Files:**
- Create: `app/alarm.py`
- Create: `tests/test_alarm.py`

- [ ] **Step 1: Alarm testlerini yaz**

`tests/test_alarm.py`:
```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.alarm import AlarmManager, AlarmLevel


@pytest.fixture
def alarm_manager():
    """GPIO mock ile AlarmManager."""
    db = AsyncMock()
    config = AsyncMock()
    config.get = AsyncMock(side_effect=lambda k: {
        "threshold_high": "0.5",
        "threshold_high_high": "1.0",
        "alarm_high_actions": "buzzer,light",
        "alarm_high_high_actions": "buzzer,light,emergency",
        "alarm_buzzer_enabled": "true",
        "alarm_email_enabled": "false",
        "gpio_buzzer_pin": "17",
        "gpio_light_pin": "27",
        "gpio_emergency_pin": "22",
    }.get(k))

    with patch("app.alarm.OutputDevice") as mock_gpio:
        mock_gpio.return_value = MagicMock()
        manager = AlarmManager(db=db, config=config)
    return manager


@pytest.mark.asyncio
async def test_no_alarm_below_threshold(alarm_manager):
    """Eşik altında alarm tetiklenmemeli."""
    await alarm_manager.init()
    level = await alarm_manager.check(0.3)
    assert level is None


@pytest.mark.asyncio
async def test_high_alarm(alarm_manager):
    """High eşiğinde alarm tetiklenmeli."""
    await alarm_manager.init()
    level = await alarm_manager.check(0.6)
    assert level == AlarmLevel.HIGH


@pytest.mark.asyncio
async def test_high_high_alarm(alarm_manager):
    """High-High eşiğinde alarm tetiklenmeli."""
    await alarm_manager.init()
    level = await alarm_manager.check(1.5)
    assert level == AlarmLevel.HIGH_HIGH


@pytest.mark.asyncio
async def test_alarm_not_retriggered(alarm_manager):
    """Aynı seviye tekrar tetiklenmemeli."""
    await alarm_manager.init()
    level1 = await alarm_manager.check(0.6)
    assert level1 == AlarmLevel.HIGH
    level2 = await alarm_manager.check(0.7)
    assert level2 is None  # Zaten aktif, tekrar tetiklenmez


@pytest.mark.asyncio
async def test_alarm_clears_below_threshold(alarm_manager):
    """Eşik altına düşünce alarm temizlenmeli ve tekrar tetiklenebilmeli."""
    await alarm_manager.init()
    await alarm_manager.check(0.6)  # HIGH tetikle
    await alarm_manager.check(0.3)  # Eşik altı — temizle
    level = await alarm_manager.check(0.6)  # Tekrar tetiklenebilmeli
    assert level == AlarmLevel.HIGH


@pytest.mark.asyncio
async def test_alarm_logged_to_db(alarm_manager):
    """Alarm tetiklenince DB'ye yazılmalı."""
    await alarm_manager.init()
    await alarm_manager.check(0.6)
    alarm_manager._db.execute.assert_called_once()
    call_args = alarm_manager._db.execute.call_args
    assert "alarm_log" in call_args[0][0]
```

- [ ] **Step 2: Testlerin fail ettiğini doğrula**

```bash
python -m pytest tests/test_alarm.py -v
```

Expected: FAIL — `app.alarm` modülü yok.

- [ ] **Step 3: `app/alarm.py` implementasyonu**

```python
"""Alarm yönetimi — eşik kontrolü, GPIO çıkışları, e-posta."""
import asyncio
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from enum import Enum

logger = logging.getLogger(__name__)

try:
    from gpiozero import OutputDevice
except ImportError:
    # GPIO olmayan ortamda (test, geliştirme) mock
    class OutputDevice:
        def __init__(self, pin, **kwargs):
            self.pin = pin
        def on(self): pass
        def off(self): pass
        def close(self): pass


class AlarmLevel(Enum):
    HIGH = "high"
    HIGH_HIGH = "high_high"


class AlarmManager:
    def __init__(self, db, config):
        self._db = db
        self._config = config
        self._active_level: AlarmLevel | None = None
        self._gpio_devices: dict[str, OutputDevice] = {}
        self._buzzer_task: asyncio.Task | None = None

    async def init(self):
        """GPIO cihazlarını başlat."""
        pin_keys = {
            "buzzer": "gpio_buzzer_pin",
            "light": "gpio_light_pin",
            "emergency": "gpio_emergency_pin",
        }
        for name, key in pin_keys.items():
            pin = await self._config.get(key)
            if pin:
                self._gpio_devices[name] = OutputDevice(int(pin), initial_value=False)

    async def check(self, dose_rate: float) -> AlarmLevel | None:
        """Doz hızını kontrol et. Alarm tetiklenirse seviyeyi döndür."""
        high = float(await self._config.get("threshold_high") or "0.5")
        high_high = float(await self._config.get("threshold_high_high") or "1.0")

        # Eşik altına düştüyse temizle
        if dose_rate < high:
            if self._active_level is not None:
                await self._clear_alarm()
            return None

        # Seviyeyi belirle
        if dose_rate >= high_high:
            new_level = AlarmLevel.HIGH_HIGH
        else:
            new_level = AlarmLevel.HIGH

        # Zaten aynı seviyede aktifse tekrar tetikleme
        if self._active_level == new_level:
            return None

        # Yeni alarm tetikle
        self._active_level = new_level
        await self._trigger_alarm(new_level, dose_rate)
        return new_level

    async def _trigger_alarm(self, level: AlarmLevel, dose_rate: float):
        """Alarm aksiyonlarını çalıştır."""
        actions_key = f"alarm_{level.value}_actions"
        actions_str = await self._config.get(actions_key) or ""
        actions = [a.strip() for a in actions_str.split(",") if a.strip()]

        # GPIO çıkışlarını aktifle
        for action in actions:
            if action in self._gpio_devices:
                self._gpio_devices[action].on()

        # Buzzer pattern'i başlat
        if "buzzer" in actions:
            if self._buzzer_task:
                self._buzzer_task.cancel()
            if level == AlarmLevel.HIGH:
                self._buzzer_task = asyncio.create_task(self._buzzer_pattern_high())
            # HIGH_HIGH: buzzer sürekli açık kalır (on() zaten çağrıldı)

        # DB'ye kaydet
        timestamp = datetime.now(timezone.utc).isoformat()
        action_taken = ",".join(actions)
        await self._db.execute(
            "INSERT INTO alarm_log (timestamp, level, dose_rate, action_taken) VALUES (?, ?, ?, ?)",
            (timestamp, level.value, dose_rate, action_taken),
        )

        # E-posta gönder
        email_enabled = await self._config.get("alarm_email_enabled")
        if email_enabled == "true":
            await self._send_email(level, dose_rate)

        logger.warning("ALARM %s: %.3f µSv/h — aksiyonlar: %s", level.value, dose_rate, action_taken)

    async def _clear_alarm(self):
        """Aktif alarmı temizle, GPIO'ları kapat."""
        if self._buzzer_task:
            self._buzzer_task.cancel()
            self._buzzer_task = None
        for device in self._gpio_devices.values():
            device.off()
        logger.info("Alarm temizlendi (önceki seviye: %s)", self._active_level)
        self._active_level = None

    async def _buzzer_pattern_high(self):
        """High alarm buzzer pattern: 1s açık, 5s kapalı."""
        buzzer = self._gpio_devices.get("buzzer")
        if not buzzer:
            return
        try:
            while True:
                buzzer.on()
                await asyncio.sleep(1)
                buzzer.off()
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            buzzer.off()

    async def _send_email(self, level: AlarmLevel, dose_rate: float):
        """SMTP ile alarm e-postası gönder."""
        try:
            to_addr = await self._config.get("alarm_email_to")
            host = await self._config.get("smtp_host")
            port = int(await self._config.get("smtp_port") or "587")
            user = await self._config.get("smtp_user")
            password = await self._config.get("smtp_pass")

            if not all([to_addr, host, user, password]):
                logger.warning("E-posta ayarları eksik, gönderilemiyor")
                return

            msg = EmailMessage()
            msg["Subject"] = f"[mssRadMon] ALARM {level.value.upper()}: {dose_rate:.3f} µSv/h"
            msg["From"] = user
            msg["To"] = to_addr
            msg.set_content(
                f"Radyasyon alarmı tetiklendi.\n\n"
                f"Seviye: {level.value.upper()}\n"
                f"Doz Hızı: {dose_rate:.3f} µSv/h\n"
                f"Zaman: {datetime.now(timezone.utc).isoformat()}\n"
                f"Cihaz: GSNJR400"
            )

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._smtp_send, host, port, user, password, msg)
            logger.info("Alarm e-postası gönderildi: %s", to_addr)
        except Exception as e:
            logger.error("E-posta gönderme hatası: %s", e)

    @staticmethod
    def _smtp_send(host, port, user, password, msg):
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)

    def shutdown(self):
        """GPIO'ları kapat."""
        if self._buzzer_task:
            self._buzzer_task.cancel()
        for device in self._gpio_devices.values():
            device.off()
            device.close()
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

```bash
python -m pytest tests/test_alarm.py -v
```

Expected: 6 PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/alarm.py tests/test_alarm.py
git commit -m "feat: alarm sistemi — eşik kontrolü, GPIO, e-posta"
```

---

## Task 6: Remote Log Forwarding (remote_log.py)

**Files:**
- Create: `app/remote_log.py`
- Create: `tests/test_remote_log.py`

- [ ] **Step 1: Remote log testlerini yaz**

`tests/test_remote_log.py`:
```python
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.remote_log import RemoteLogForwarder


@pytest.fixture
def forwarder():
    db = AsyncMock()
    config = AsyncMock()
    config.get = AsyncMock(side_effect=lambda k: {
        "remote_log_enabled": "true",
        "remote_log_url": "http://example.com/api",
        "remote_log_api_key": "test-key",
    }.get(k))
    return RemoteLogForwarder(db=db, config=config)


@pytest.mark.asyncio
async def test_disabled_does_nothing(forwarder):
    """remote_log_enabled=false ise hiçbir şey yapmamalı."""
    forwarder._config.get = AsyncMock(side_effect=lambda k: {
        "remote_log_enabled": "false",
        "remote_log_url": "",
        "remote_log_api_key": "",
    }.get(k))
    with patch("aiohttp.ClientSession") as mock_session:
        await forwarder.forward_reading(
            timestamp="2026-03-31T12:00:00Z", dose_rate=0.12, cumulative_dose=45.6, row_id=1
        )
        mock_session.assert_not_called()


@pytest.mark.asyncio
async def test_forward_reading_success(forwarder):
    """Başarılı push sonrası remote_synced=1 yapılmalı."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await forwarder.forward_reading(
            timestamp="2026-03-31T12:00:00Z", dose_rate=0.12, cumulative_dose=45.6, row_id=1
        )

    # remote_synced=1 güncellenmeli
    forwarder._db.execute.assert_called_with(
        "UPDATE readings SET remote_synced = 1 WHERE id = ?", (1,)
    )


@pytest.mark.asyncio
async def test_sync_unsynced_readings(forwarder):
    """Senkronize edilmemiş kayıtları batch olarak göndermeli."""
    forwarder._db.fetch_all = AsyncMock(return_value=[
        {"id": 1, "timestamp": "2026-03-31T10:00:00Z", "dose_rate": 0.10, "cumulative_dose": 10.0},
        {"id": 2, "timestamp": "2026-03-31T10:00:10Z", "dose_rate": 0.11, "cumulative_dose": 10.5},
    ])

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await forwarder.sync_unsynced()

    assert forwarder._db.execute.call_count == 2  # Her satır için UPDATE
```

- [ ] **Step 2: Testlerin fail ettiğini doğrula**

```bash
python -m pytest tests/test_remote_log.py -v
```

Expected: FAIL — `app.remote_log` modülü yok.

- [ ] **Step 3: `app/remote_log.py` implementasyonu**

```python
"""Remote log forwarding — HTTP POST ile uzak sunucuya veri iletimi."""
import asyncio
import logging

import aiohttp

logger = logging.getLogger(__name__)

DEVICE_ID = "GSNJR400"
BATCH_SIZE = 100
RETRY_DELAYS = [5, 15, 45]


class RemoteLogForwarder:
    def __init__(self, db, config):
        self._db = db
        self._config = config

    async def _is_enabled(self) -> bool:
        return (await self._config.get("remote_log_enabled")) == "true"

    async def _get_url(self) -> str:
        return await self._config.get("remote_log_url") or ""

    async def _get_api_key(self) -> str:
        return await self._config.get("remote_log_api_key") or ""

    async def forward_reading(self, timestamp: str, dose_rate: float,
                               cumulative_dose: float, row_id: int):
        """Tek bir okumayı uzak sunucuya gönder."""
        if not await self._is_enabled():
            return

        url = await self._get_url()
        api_key = await self._get_api_key()
        if not url:
            return

        payload = {
            "device_id": DEVICE_ID,
            "timestamp": timestamp,
            "dose_rate": dose_rate,
            "cumulative_dose": cumulative_dose,
        }

        success = await self._post(f"{url}/reading", api_key, payload)
        if success:
            await self._db.execute(
                "UPDATE readings SET remote_synced = 1 WHERE id = ?", (row_id,)
            )

    async def forward_alarm(self, timestamp: str, level: str,
                             dose_rate: float, action_taken: str, row_id: int):
        """Tek bir alarm kaydını uzak sunucuya gönder."""
        if not await self._is_enabled():
            return

        url = await self._get_url()
        api_key = await self._get_api_key()
        if not url:
            return

        payload = {
            "device_id": DEVICE_ID,
            "timestamp": timestamp,
            "level": level,
            "dose_rate": dose_rate,
            "action_taken": action_taken,
        }

        success = await self._post(f"{url}/alarm", api_key, payload)
        if success:
            await self._db.execute(
                "UPDATE alarm_log SET remote_synced = 1 WHERE id = ?", (row_id,)
            )

    async def sync_unsynced(self):
        """Senkronize edilmemiş tüm kayıtları batch halinde gönder."""
        if not await self._is_enabled():
            return

        # Okumaları senkronize et
        rows = await self._db.fetch_all(
            "SELECT id, timestamp, dose_rate, cumulative_dose FROM readings "
            "WHERE remote_synced = 0 ORDER BY timestamp LIMIT ?",
            (BATCH_SIZE,),
        )
        for row in rows:
            await self.forward_reading(
                row["timestamp"], row["dose_rate"], row["cumulative_dose"], row["id"]
            )

        # Alarmları senkronize et
        alarm_rows = await self._db.fetch_all(
            "SELECT id, timestamp, level, dose_rate, action_taken FROM alarm_log "
            "WHERE remote_synced = 0 ORDER BY timestamp LIMIT ?",
            (BATCH_SIZE,),
        )
        for row in alarm_rows:
            await self.forward_alarm(
                row["timestamp"], row["level"], row["dose_rate"],
                row["action_taken"], row["id"]
            )

    async def _post(self, url: str, api_key: str, payload: dict) -> bool:
        """HTTP POST ile veri gönder. Retry mekanizması ile."""
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

        for attempt, delay in enumerate(RETRY_DELAYS):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            return True
                        logger.warning("Remote log POST %s: HTTP %d (deneme %d)", url, resp.status, attempt + 1)
            except Exception as e:
                logger.warning("Remote log POST hatası: %s (deneme %d)", e, attempt + 1)

            if attempt < len(RETRY_DELAYS) - 1:
                await asyncio.sleep(delay)

        logger.error("Remote log POST başarısız: %s (%d deneme tükendi)", url, len(RETRY_DELAYS))
        return False

    async def run_sync_loop(self, interval: int = 60):
        """Periyodik senkronizasyon döngüsü."""
        while True:
            try:
                await self.sync_unsynced()
            except Exception as e:
                logger.error("Sync döngüsü hatası: %s", e)
            await asyncio.sleep(interval)
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

```bash
python -m pytest tests/test_remote_log.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/remote_log.py tests/test_remote_log.py
git commit -m "feat: remote log forwarding — persistent queue ile catch-up"
```

---

## Task 7: FastAPI Uygulama Çekirdeği (main.py)

**Files:**
- Create: `app/main.py`

- [ ] **Step 1: `app/main.py` implementasyonu**

```python
"""mssRadMon — FastAPI uygulama giriş noktası."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.alarm import AlarmManager
from app.config import Config
from app.db import Database
from app.remote_log import RemoteLogForwarder
from app.routers import admin, api, ws
from app.serial_reader import GammaScoutReader, Reading

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
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        db = Database(DB_PATH)
        await db.init()
        config = Config(db)
        await config.init()

        alarm_manager = AlarmManager(db=db, config=config)
        await alarm_manager.init()

        remote_log = RemoteLogForwarder(db=db, config=config)

        reader = GammaScoutReader()

        # App state'e ata
        app.state.db = db
        app.state.config = config
        app.state.alarm = alarm_manager
        app.state.remote_log = remote_log
        app.state.reader = reader
        app.state.ws_clients = set()

        async def on_reading(reading: Reading):
            """Yeni okuma geldiğinde çağrılır."""
            row_id = await db.execute(
                "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
                (reading.timestamp, reading.dose_rate, reading.cumulative_dose),
            )
            # Alarm kontrolü
            await alarm_manager.check(reading.dose_rate)
            # WebSocket push
            msg = {
                "type": "reading",
                "timestamp": reading.timestamp,
                "dose_rate": reading.dose_rate,
                "cumulative_dose": reading.cumulative_dose,
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

        logger.info("mssRadMon başlatıldı — interval=%ds", interval)
        yield

        # Shutdown
        reader.stop()
        reader_task.cancel()
        sync_task.cancel()
        alarm_manager.shutdown()
        await db.close()
        logger.info("mssRadMon kapatıldı")

    app = FastAPI(title="mssRadMon", lifespan=lifespan)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    app.include_router(api.router)
    app.include_router(ws.router)
    app.include_router(admin.router)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=False)
```

- [ ] **Step 2: Commit**

```bash
git add app/main.py
git commit -m "feat: FastAPI uygulama çekirdeği — lifespan, background tasks"
```

---

## Task 8: REST API Endpointleri (routers/api.py)

**Files:**
- Create: `app/routers/api.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: API testlerini yaz**

`tests/test_api.py`:
```python
import pytest
import pytest_asyncio

from app.db import Database
from app.config import Config


@pytest_asyncio.fixture
async def seeded_db(test_db_path):
    """Test verileri ile doldurulmuş DB."""
    db = Database(test_db_path)
    await db.init()
    config = Config(db)
    await config.init()

    # Ölçüm verileri ekle
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-03-31T10:00:00Z", 0.10, 10.0),
    )
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-03-31T12:00:00Z", 0.15, 20.0),
    )
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-03-31T23:00:00Z", 0.12, 30.0),
    )

    # Alarm ekle
    await db.execute(
        "INSERT INTO alarm_log (timestamp, level, dose_rate, action_taken) VALUES (?, ?, ?, ?)",
        ("2026-03-31T12:00:00Z", "high", 0.55, "buzzer,light"),
    )

    yield db, config
    await db.close()


@pytest.mark.asyncio
async def test_get_current(seeded_db):
    """GET /api/current son okumayı döndürmeli."""
    from app.routers.api import get_current
    from unittest.mock import MagicMock

    db, config = seeded_db
    request = MagicMock()
    request.app.state.db = db
    request.app.state.reader = MagicMock()
    request.app.state.reader.connected = True

    result = await get_current(request)
    assert result["dose_rate"] == 0.12
    assert result["cumulative_dose"] == 30.0


@pytest.mark.asyncio
async def test_get_alarms(seeded_db):
    """GET /api/alarms alarm geçmişini döndürmeli."""
    from app.routers.api import get_alarms
    from unittest.mock import MagicMock

    db, config = seeded_db
    request = MagicMock()
    request.app.state.db = db

    result = await get_alarms(request, last="24h")
    assert len(result) == 1
    assert result[0]["level"] == "high"
```

- [ ] **Step 2: Testlerin fail ettiğini doğrula**

```bash
python -m pytest tests/test_api.py -v
```

Expected: FAIL — `app.routers.api` modülü yok.

- [ ] **Step 3: `app/routers/api.py` implementasyonu**

```python
"""REST API endpointleri."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request

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
    if row:
        return {
            "timestamp": row["timestamp"],
            "dose_rate": row["dose_rate"],
            "cumulative_dose": row["cumulative_dose"],
            "connected": connected,
        }
    return {"timestamp": None, "dose_rate": None, "cumulative_dose": None, "connected": connected}


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

    # Bugünün ilk ve son okumasını al
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


@router.get("/status")
async def get_status(request: Request):
    """Cihaz ve uygulama durumunu döndür."""
    reader = request.app.state.reader
    return {
        "connected": reader.connected,
        "port": reader.port,
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
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

```bash
python -m pytest tests/test_api.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/routers/api.py tests/test_api.py
git commit -m "feat: REST API endpointleri — current, readings, daily-dose, status, alarms"
```

---

## Task 9: WebSocket Endpoint (routers/ws.py)

**Files:**
- Create: `app/routers/ws.py`
- Create: `tests/test_ws.py`

- [ ] **Step 1: WebSocket testini yaz**

`tests/test_ws.py`:
```python
import pytest

from app.routers.ws import router


def test_ws_router_exists():
    """WebSocket router doğru tanımlanmış olmalı."""
    routes = [r.path for r in router.routes]
    assert "/ws/live" in routes
```

- [ ] **Step 2: Testin fail ettiğini doğrula**

```bash
python -m pytest tests/test_ws.py -v
```

Expected: FAIL — `app.routers.ws` modülü yok.

- [ ] **Step 3: `app/routers/ws.py` implementasyonu**

```python
"""WebSocket endpoint — canlı veri akışı."""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """Canlı veri akışı WebSocket endpoint'i."""
    await websocket.accept()
    clients = websocket.app.state.ws_clients
    clients.add(websocket)
    logger.info("WebSocket client bağlandı (toplam: %d)", len(clients))
    try:
        while True:
            # Client'tan gelen mesajları dinle (keep-alive)
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(websocket)
        logger.info("WebSocket client ayrıldı (toplam: %d)", len(clients))
```

- [ ] **Step 4: Testin geçtiğini doğrula**

```bash
python -m pytest tests/test_ws.py -v
```

Expected: 1 PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/routers/ws.py tests/test_ws.py
git commit -m "feat: WebSocket canlı veri akışı endpoint'i"
```

---

## Task 10: Admin API Endpointleri (routers/admin.py)

**Files:**
- Create: `app/routers/admin.py`
- Create: `tests/test_admin.py`

- [ ] **Step 1: Admin testlerini yaz**

`tests/test_admin.py`:
```python
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock

from app.db import Database
from app.config import Config


@pytest_asyncio.fixture
async def admin_deps(test_db_path):
    db = Database(test_db_path)
    await db.init()
    config = Config(db)
    await config.init()
    yield db, config
    await db.close()


@pytest.mark.asyncio
async def test_get_settings(admin_deps):
    """GET /api/settings tüm ayarları döndürmeli."""
    from app.routers.admin import get_settings

    db, config = admin_deps
    request = MagicMock()
    request.app.state.config = config

    result = await get_settings(request)
    assert result["sampling_interval"] == "10"
    assert result["threshold_high"] == "0.5"


@pytest.mark.asyncio
async def test_update_settings(admin_deps):
    """PUT /api/settings ayarları güncellemeli."""
    from app.routers.admin import update_settings

    db, config = admin_deps
    request = MagicMock()
    request.app.state.config = config

    result = await update_settings(request, {"threshold_high": "0.8", "sampling_interval": "30"})
    assert result["status"] == "ok"

    val = await config.get("threshold_high")
    assert val == "0.8"
    val2 = await config.get("sampling_interval")
    assert val2 == "30"
```

- [ ] **Step 2: Testlerin fail ettiğini doğrula**

```bash
python -m pytest tests/test_admin.py -v
```

Expected: FAIL — `app.routers.admin` modülü yok.

- [ ] **Step 3: `app/routers/admin.py` implementasyonu**

```python
"""Admin API endpointleri — ayar yönetimi."""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/settings")
async def get_settings(request: Request):
    """Tüm ayarları döndür."""
    config = request.app.state.config
    return await config.get_all()


@router.put("/settings")
async def update_settings(request: Request, settings: dict):
    """Ayarları güncelle."""
    config = request.app.state.config
    for key, value in settings.items():
        await config.set(key, str(value))
    return {"status": "ok"}
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

```bash
python -m pytest tests/test_admin.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/routers/admin.py tests/test_admin.py
git commit -m "feat: admin API — ayar okuma/yazma endpointleri"
```

---

## Task 11: Dashboard Sayfası (templates + static)

**Files:**
- Create: `app/templates/base.html`
- Create: `app/templates/dashboard.html`
- Create: `app/static/css/style.css`
- Create: `app/static/js/dashboard.js`

- [ ] **Step 1: Chart.js indir**

```bash
mkdir -p /home/alper/mssRadMon/app/static/lib
curl -L -o /home/alper/mssRadMon/app/static/lib/chart.js https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js
```

- [ ] **Step 2: `app/templates/base.html` oluştur**

```html
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}mssRadMon{% endblock %}</title>
    <link rel="stylesheet" href="/static/css/style.css">
    {% block head %}{% endblock %}
</head>
<body>
    <nav class="navbar">
        <div class="nav-brand">mssRadMon</div>
        <div class="nav-links">
            <a href="/" class="{% if active == 'dashboard' %}active{% endif %}">Gösterge Paneli</a>
            <a href="/admin" class="{% if active == 'admin' %}active{% endif %}">Yönetim</a>
        </div>
    </nav>
    <main class="container">
        {% block content %}{% endblock %}
    </main>
    {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 3: `app/static/css/style.css` oluştur**

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
    --bg: #1a1a2e;
    --surface: #16213e;
    --card: #0f3460;
    --text: #e0e0e0;
    --text-dim: #a0a0a0;
    --green: #00c853;
    --yellow: #ffd600;
    --red: #ff1744;
    --accent: #00bcd4;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
}

/* Navbar */
.navbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1.5rem;
    background: var(--surface);
    border-bottom: 1px solid rgba(255,255,255,0.1);
}
.nav-brand { font-size: 1.25rem; font-weight: 700; color: var(--accent); }
.nav-links a {
    color: var(--text-dim);
    text-decoration: none;
    margin-left: 1.5rem;
    font-size: 0.9rem;
}
.nav-links a.active { color: var(--accent); }

/* Container */
.container { max-width: 960px; margin: 0 auto; padding: 1.5rem; }

/* Cards */
.card {
    background: var(--card);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
}
.card-title { font-size: 0.85rem; color: var(--text-dim); margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.05em; }

/* Dashboard grid */
.dashboard-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
    margin-bottom: 1rem;
}
@media (max-width: 600px) {
    .dashboard-grid { grid-template-columns: 1fr; }
}

/* Dose rate display */
.dose-rate-value {
    font-size: 3.5rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
}
.dose-rate-unit { font-size: 1rem; color: var(--text-dim); margin-left: 0.25rem; }

/* Status colors */
.status-normal { color: var(--green); }
.status-high { color: var(--yellow); }
.status-high-high { color: var(--red); }

/* Connection indicator */
.conn-indicator {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
}
.conn-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--red);
}
.conn-dot.connected { background: var(--green); }

/* Chart container */
.chart-container { position: relative; width: 100%; height: 250px; }

/* Daily dose */
.daily-dose-value { font-size: 2rem; font-weight: 600; }

/* Alarm banner */
.alarm-banner {
    padding: 0.75rem 1rem;
    border-radius: 8px;
    margin-bottom: 1rem;
    display: none;
}
.alarm-banner.active { display: block; }
.alarm-banner.high { background: rgba(255,214,0,0.15); border: 1px solid var(--yellow); color: var(--yellow); }
.alarm-banner.high_high { background: rgba(255,23,68,0.15); border: 1px solid var(--red); color: var(--red); }

/* Admin form */
.form-group { margin-bottom: 1rem; }
.form-group label { display: block; font-size: 0.85rem; color: var(--text-dim); margin-bottom: 0.35rem; }
.form-group input, .form-group select {
    width: 100%;
    padding: 0.5rem 0.75rem;
    background: var(--surface);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 6px;
    color: var(--text);
    font-size: 0.9rem;
}
.form-group input:focus, .form-group select:focus { outline: none; border-color: var(--accent); }

.btn {
    display: inline-block;
    padding: 0.5rem 1.25rem;
    border: none;
    border-radius: 6px;
    font-size: 0.9rem;
    cursor: pointer;
    color: #fff;
    background: var(--accent);
}
.btn:hover { opacity: 0.9; }

/* Alarm history table */
.alarm-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.alarm-table th, .alarm-table td { padding: 0.5rem; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.08); }
.alarm-table th { color: var(--text-dim); font-weight: 500; }

/* Toggle switch */
.toggle { position: relative; display: inline-block; width: 44px; height: 24px; }
.toggle input { opacity: 0; width: 0; height: 0; }
.toggle .slider {
    position: absolute; inset: 0;
    background: rgba(255,255,255,0.15);
    border-radius: 24px;
    cursor: pointer;
    transition: 0.2s;
}
.toggle .slider::before {
    content: "";
    position: absolute;
    width: 18px; height: 18px;
    left: 3px; bottom: 3px;
    background: #fff;
    border-radius: 50%;
    transition: 0.2s;
}
.toggle input:checked + .slider { background: var(--accent); }
.toggle input:checked + .slider::before { transform: translateX(20px); }
```

- [ ] **Step 4: `app/templates/dashboard.html` oluştur**

```html
{% extends "base.html" %}
{% block title %}Gösterge Paneli — mssRadMon{% endblock %}
{% block head %}
<script src="/static/lib/chart.js"></script>
{% endblock %}

{% block content %}
<div class="alarm-banner" id="alarmBanner">
    <strong id="alarmLevel"></strong>: <span id="alarmMsg"></span>
</div>

<div class="dashboard-grid">
    <div class="card">
        <div class="card-title">Anlık Doz Hızı</div>
        <div>
            <span class="dose-rate-value status-normal" id="doseRate">—</span>
            <span class="dose-rate-unit">µSv/h</span>
        </div>
    </div>
    <div class="card">
        <div class="card-title">Günlük Kümülatif Doz</div>
        <div>
            <span class="daily-dose-value" id="dailyDose">—</span>
            <span class="dose-rate-unit">µSv</span>
        </div>
    </div>
</div>

<div class="card">
    <div class="card-title">
        Son 1 Saat — Doz Hızı
        <span class="conn-indicator" style="float:right">
            <span class="conn-dot" id="connDot"></span>
            <span id="connText">Bağlantı yok</span>
        </span>
    </div>
    <div class="chart-container">
        <canvas id="doseChart"></canvas>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script src="/static/js/dashboard.js"></script>
{% endblock %}
```

- [ ] **Step 5: `app/static/js/dashboard.js` oluştur**

```javascript
"use strict";

const POLL_INTERVAL = 10000; // 10s fallback poll
const WS_RECONNECT_DELAY = 3000;

// Elements
const doseRateEl = document.getElementById("doseRate");
const dailyDoseEl = document.getElementById("dailyDose");
const connDot = document.getElementById("connDot");
const connText = document.getElementById("connText");
const alarmBanner = document.getElementById("alarmBanner");
const alarmLevel = document.getElementById("alarmLevel");
const alarmMsg = document.getElementById("alarmMsg");

// Chart setup
const ctx = document.getElementById("doseChart").getContext("2d");
const chart = new Chart(ctx, {
    type: "line",
    data: {
        labels: [],
        datasets: [{
            label: "Doz Hızı (µSv/h)",
            data: [],
            borderColor: "#00bcd4",
            backgroundColor: "rgba(0,188,212,0.1)",
            fill: true,
            tension: 0.3,
            pointRadius: 0,
        }],
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            x: {
                ticks: { color: "#a0a0a0", maxTicksLimit: 12, font: { size: 11 } },
                grid: { color: "rgba(255,255,255,0.05)" },
            },
            y: {
                ticks: { color: "#a0a0a0", font: { size: 11 } },
                grid: { color: "rgba(255,255,255,0.05)" },
                beginAtZero: true,
            },
        },
        plugins: {
            legend: { display: false },
        },
    },
});

// Thresholds (başlangıçta API'den çekilecek)
let thresholdHigh = 0.5;
let thresholdHighHigh = 1.0;

function updateDoseRate(value) {
    doseRateEl.textContent = value.toFixed(3);
    doseRateEl.className = "dose-rate-value ";
    if (value >= thresholdHighHigh) {
        doseRateEl.className += "status-high-high";
    } else if (value >= thresholdHigh) {
        doseRateEl.className += "status-high";
    } else {
        doseRateEl.className += "status-normal";
    }
}

function updateConnection(connected) {
    connDot.className = connected ? "conn-dot connected" : "conn-dot";
    connText.textContent = connected ? "Bağlı" : "Bağlantı yok";
}

function formatTime(isoStr) {
    const d = new Date(isoStr);
    return d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function addChartPoint(timestamp, value) {
    chart.data.labels.push(formatTime(timestamp));
    chart.data.datasets[0].data.push(value);

    // Son 1 saat: 10s interval = max 360 nokta
    const maxPoints = 360;
    if (chart.data.labels.length > maxPoints) {
        chart.data.labels.shift();
        chart.data.datasets[0].data.shift();
    }
    chart.update("none");
}

// Load initial data
async function loadInitial() {
    try {
        // Ayarları al (threshold için)
        const settingsRes = await fetch("/api/settings");
        const settings = await settingsRes.json();
        thresholdHigh = parseFloat(settings.threshold_high || "0.5");
        thresholdHighHigh = parseFloat(settings.threshold_high_high || "1.0");

        // Son 1 saatlik verileri al
        const readingsRes = await fetch("/api/readings?last=1h");
        const readings = await readingsRes.json();
        readings.forEach(r => addChartPoint(r.timestamp, r.dose_rate));

        // Anlık veri
        const currentRes = await fetch("/api/current");
        const current = await currentRes.json();
        if (current.dose_rate !== null) {
            updateDoseRate(current.dose_rate);
        }
        updateConnection(current.connected);

        // Günlük doz
        const dailyRes = await fetch("/api/daily-dose");
        const daily = await dailyRes.json();
        dailyDoseEl.textContent = daily.daily_dose.toFixed(3);

        // Son alarm
        const alarmsRes = await fetch("/api/alarms?last=24h");
        const alarms = await alarmsRes.json();
        if (alarms.length > 0) {
            const last = alarms[0];
            alarmBanner.className = "alarm-banner active " + last.level;
            alarmLevel.textContent = last.level === "high_high" ? "KRİTİK ALARM" : "UYARI";
            alarmMsg.textContent = `${last.dose_rate.toFixed(3)} µSv/h — ${formatTime(last.timestamp)}`;
        }
    } catch (e) {
        console.error("Başlangıç verileri yüklenemedi:", e);
    }
}

// WebSocket
let ws = null;

function connectWS() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws/live`);

    ws.onopen = () => console.log("WebSocket bağlandı");

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "reading") {
            updateDoseRate(msg.dose_rate);
            addChartPoint(msg.timestamp, msg.dose_rate);
            // Günlük dozu yeniden hesapla (basit: API'den çek)
            fetch("/api/daily-dose")
                .then(r => r.json())
                .then(d => { dailyDoseEl.textContent = d.daily_dose.toFixed(3); });
        }
    };

    ws.onclose = () => {
        console.log("WebSocket kapandı, yeniden bağlanılıyor...");
        setTimeout(connectWS, WS_RECONNECT_DELAY);
    };

    ws.onerror = () => ws.close();
}

// Fallback poll (WebSocket yoksa)
setInterval(async () => {
    if (ws && ws.readyState === WebSocket.OPEN) return;
    try {
        const res = await fetch("/api/current");
        const data = await res.json();
        if (data.dose_rate !== null) {
            updateDoseRate(data.dose_rate);
            addChartPoint(data.timestamp, data.dose_rate);
        }
        updateConnection(data.connected);
    } catch (e) { /* ignore */ }
}, POLL_INTERVAL);

// Status poll (bağlantı durumu için)
setInterval(async () => {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();
        updateConnection(data.connected);
    } catch (e) { /* ignore */ }
}, 5000);

// Start
loadInitial();
connectWS();
```

- [ ] **Step 6: Template route'larını ekle — `app/routers/api.py`'ye sayfa endpointleri ekle**

`app/routers/api.py` dosyasının sonuna ekle:

```python
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"))


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "active": "dashboard"})
```

Not: Bu route `/api` prefix'i dışında olmalı. `app/main.py`'ye ayrı bir route olarak ekle:

Aslında daha temiz olması için page route'larını `main.py`'ye ekleyelim:

`app/main.py`'nin `create_app` fonksiyonunda, router'lar include edildikten sonra:

```python
from fastapi.responses import HTMLResponse

templates = Jinja2Templates(directory=TEMPLATE_DIR)

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "active": "dashboard"})

@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request, "active": "admin"})
```

- [ ] **Step 7: Commit**

```bash
git add app/templates/ app/static/ app/main.py
git commit -m "feat: dashboard sayfası — anlık gösterge, grafik, günlük doz"
```

---

## Task 12: Admin Sayfası

**Files:**
- Create: `app/templates/admin.html`
- Create: `app/static/js/admin.js`

- [ ] **Step 1: `app/templates/admin.html` oluştur**

```html
{% extends "base.html" %}
{% block title %}Yönetim — mssRadMon{% endblock %}

{% block content %}
<h2 style="margin-bottom: 1rem;">Yönetim Paneli</h2>

<div class="card">
    <div class="card-title">Örnekleme</div>
    <div class="form-group">
        <label for="sampling_interval">Örnekleme Aralığı (saniye)</label>
        <input type="number" id="sampling_interval" min="1" max="3600">
    </div>
</div>

<div class="card">
    <div class="card-title">Alarm Eşik Değerleri</div>
    <div class="dashboard-grid">
        <div class="form-group">
            <label for="threshold_high">High Eşiği (µSv/h)</label>
            <input type="number" id="threshold_high" step="0.01" min="0">
        </div>
        <div class="form-group">
            <label for="threshold_high_high">High-High Eşiği (µSv/h)</label>
            <input type="number" id="threshold_high_high" step="0.01" min="0">
        </div>
    </div>
    <div class="dashboard-grid">
        <div class="form-group">
            <label for="alarm_high_actions">High Aksiyonları</label>
            <input type="text" id="alarm_high_actions" placeholder="buzzer,light">
        </div>
        <div class="form-group">
            <label for="alarm_high_high_actions">High-High Aksiyonları</label>
            <input type="text" id="alarm_high_high_actions" placeholder="buzzer,light,emergency">
        </div>
    </div>
</div>

<div class="card">
    <div class="card-title">GPIO Pin Ayarları</div>
    <div class="dashboard-grid">
        <div class="form-group">
            <label for="gpio_buzzer_pin">Buzzer Pin</label>
            <input type="number" id="gpio_buzzer_pin" min="0" max="40">
        </div>
        <div class="form-group">
            <label for="gpio_light_pin">Işık Pin</label>
            <input type="number" id="gpio_light_pin" min="0" max="40">
        </div>
    </div>
    <div class="form-group" style="max-width:calc(50% - 0.5rem);">
        <label for="gpio_emergency_pin">Acil Kapatma Pin</label>
        <input type="number" id="gpio_emergency_pin" min="0" max="40">
    </div>
</div>

<div class="card">
    <div class="card-title">Buzzer Ayarı</div>
    <div class="form-group">
        <label>
            <span class="toggle">
                <input type="checkbox" id="alarm_buzzer_enabled">
                <span class="slider"></span>
            </span>
            Buzzer Aktif
        </label>
    </div>
</div>

<div class="card">
    <div class="card-title">E-posta Bildirimi</div>
    <div class="form-group">
        <label>
            <span class="toggle">
                <input type="checkbox" id="alarm_email_enabled">
                <span class="slider"></span>
            </span>
            E-posta Bildirimi Aktif
        </label>
    </div>
    <div class="form-group">
        <label for="alarm_email_to">Alıcı Adresi</label>
        <input type="email" id="alarm_email_to">
    </div>
    <div class="dashboard-grid">
        <div class="form-group">
            <label for="smtp_host">SMTP Sunucu</label>
            <input type="text" id="smtp_host">
        </div>
        <div class="form-group">
            <label for="smtp_port">SMTP Port</label>
            <input type="number" id="smtp_port">
        </div>
    </div>
    <div class="dashboard-grid">
        <div class="form-group">
            <label for="smtp_user">SMTP Kullanıcı</label>
            <input type="text" id="smtp_user">
        </div>
        <div class="form-group">
            <label for="smtp_pass">SMTP Şifre</label>
            <input type="password" id="smtp_pass">
        </div>
    </div>
</div>

<div class="card">
    <div class="card-title">Uzak Log Sunucusu</div>
    <div class="form-group">
        <label>
            <span class="toggle">
                <input type="checkbox" id="remote_log_enabled">
                <span class="slider"></span>
            </span>
            Uzak Log Aktif
        </label>
    </div>
    <div class="form-group">
        <label for="remote_log_url">Endpoint URL</label>
        <input type="url" id="remote_log_url">
    </div>
    <div class="form-group">
        <label for="remote_log_api_key">API Anahtarı</label>
        <input type="text" id="remote_log_api_key">
    </div>
</div>

<button class="btn" id="saveBtn" style="margin-bottom: 2rem;">Ayarları Kaydet</button>
<div id="saveMsg" style="margin-top: 0.5rem; font-size: 0.85rem; color: var(--green); display: none;">Ayarlar kaydedildi.</div>

<div class="card">
    <div class="card-title">Alarm Geçmişi (Son 24 Saat)</div>
    <table class="alarm-table">
        <thead>
            <tr><th>Zaman</th><th>Seviye</th><th>Doz Hızı</th><th>Aksiyonlar</th></tr>
        </thead>
        <tbody id="alarmTableBody">
        </tbody>
    </table>
</div>
{% endblock %}

{% block scripts %}
<script src="/static/js/admin.js"></script>
{% endblock %}
```

- [ ] **Step 2: `app/static/js/admin.js` oluştur**

```javascript
"use strict";

// Tüm ayar alanlarının ID listesi
const FIELDS = [
    "sampling_interval", "threshold_high", "threshold_high_high",
    "alarm_high_actions", "alarm_high_high_actions",
    "gpio_buzzer_pin", "gpio_light_pin", "gpio_emergency_pin",
    "alarm_buzzer_enabled", "alarm_email_enabled",
    "alarm_email_to", "smtp_host", "smtp_port", "smtp_user", "smtp_pass",
    "remote_log_enabled", "remote_log_url", "remote_log_api_key",
];

const TOGGLE_FIELDS = ["alarm_buzzer_enabled", "alarm_email_enabled", "remote_log_enabled"];

async function loadSettings() {
    try {
        const res = await fetch("/api/settings");
        const settings = await res.json();

        FIELDS.forEach(key => {
            const el = document.getElementById(key);
            if (!el) return;
            if (TOGGLE_FIELDS.includes(key)) {
                el.checked = settings[key] === "true";
            } else {
                el.value = settings[key] || "";
            }
        });
    } catch (e) {
        console.error("Ayarlar yüklenemedi:", e);
    }
}

async function saveSettings() {
    const payload = {};
    FIELDS.forEach(key => {
        const el = document.getElementById(key);
        if (!el) return;
        if (TOGGLE_FIELDS.includes(key)) {
            payload[key] = el.checked ? "true" : "false";
        } else {
            payload[key] = el.value;
        }
    });

    try {
        const res = await fetch("/api/settings", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (res.ok) {
            const msg = document.getElementById("saveMsg");
            msg.style.display = "block";
            setTimeout(() => { msg.style.display = "none"; }, 3000);
        }
    } catch (e) {
        console.error("Ayarlar kaydedilemedi:", e);
    }
}

async function loadAlarmHistory() {
    try {
        const res = await fetch("/api/alarms?last=24h");
        const alarms = await res.json();
        const tbody = document.getElementById("alarmTableBody");
        tbody.innerHTML = "";

        if (alarms.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-dim)">Son 24 saatte alarm yok</td></tr>';
            return;
        }

        alarms.forEach(a => {
            const d = new Date(a.timestamp);
            const timeStr = d.toLocaleString("tr-TR");
            const levelStr = a.level === "high_high" ? "KRİTİK" : "UYARI";
            const row = document.createElement("tr");
            row.innerHTML = `<td>${timeStr}</td><td>${levelStr}</td><td>${a.dose_rate.toFixed(3)} µSv/h</td><td>${a.action_taken}</td>`;
            tbody.appendChild(row);
        });
    } catch (e) {
        console.error("Alarm geçmişi yüklenemedi:", e);
    }
}

document.getElementById("saveBtn").addEventListener("click", saveSettings);

loadSettings();
loadAlarmHistory();
```

- [ ] **Step 3: Commit**

```bash
git add app/templates/admin.html app/static/js/admin.js
git commit -m "feat: admin sayfası — ayarlar formu ve alarm geçmişi"
```

---

## Task 13: systemd Service ve README

**Files:**
- Create: `systemd/mssradmon.service`
- Create: `README.md`

- [ ] **Step 1: `systemd/mssradmon.service` oluştur**

```ini
[Unit]
Description=mssRadMon - GammaScout Radyasyon Monitörü
After=network.target

[Service]
Type=simple
User=alper
WorkingDirectory=/home/alper/mssRadMon
ExecStart=/home/alper/mssRadMon/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: `README.md` oluştur**

```markdown
# mssRadMon

GammaScout Online USB radyasyon ölçer için Raspberry Pi tabanlı izleme sistemi.

## Özellikler

- Anlık doz hızı ve kümülatif doz takibi
- Canlı web dashboard (WebSocket + REST API)
- İki seviyeli alarm sistemi (High / High-High)
- GPIO çıkışları: buzzer, ışık, acil kapatma
- E-posta bildirimleri (SMTP)
- Uzak sunucuya log iletimi (HTTP POST, persistent queue)
- Yapılandırılabilir ayarlar (web admin paneli)

## Kurulum

```bash
cd /home/alper/mssRadMon
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Çalıştırma

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Tarayıcıda: `http://<rpi-ip>:8080`

## systemd ile Servis Olarak Kurma

```bash
sudo cp systemd/mssradmon.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mssradmon
sudo systemctl start mssradmon
```

## Geliştirme

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

## API

| Endpoint | Açıklama |
|----------|----------|
| `GET /api/current` | Son ölçüm |
| `GET /api/readings?last=1h` | Zaman aralığına göre okumalar |
| `GET /api/daily-dose` | Günlük kümülatif doz |
| `GET /api/status` | Cihaz durumu |
| `GET /api/alarms?last=24h` | Alarm geçmişi |
| `GET /api/settings` | Tüm ayarlar |
| `PUT /api/settings` | Ayar güncelleme |
| `WS /ws/live` | Canlı veri akışı |

## Donanım

- Raspberry Pi 5
- GammaScout Online (USB)
- GPIO 17: Buzzer
- GPIO 27: Uyarı ışığı
- GPIO 22: Acil kapatma rölesi
```

- [ ] **Step 3: Commit**

```bash
git add systemd/mssradmon.service README.md
git commit -m "docs: systemd service dosyası ve README"
```

---

## Task 14: Entegrasyon Testi ve Son Doğrulama

- [ ] **Step 1: Tüm testleri çalıştır**

```bash
cd /home/alper/mssRadMon
source .venv/bin/activate
python -m pytest tests/ -v
```

Expected: Tüm testler PASSED.

- [ ] **Step 2: Uygulama başlatma testi (serial mock ile)**

Cihaz bağlı olmadan uygulamanın çökmeden başladığını doğrula:

```bash
MSSRADMON_DB_PATH=data/test.db python -m uvicorn app.main:app --host 127.0.0.1 --port 8080 &
sleep 3
curl -s http://127.0.0.1:8080/api/status | python3 -m json.tool
curl -s http://127.0.0.1:8080/api/settings | python3 -m json.tool
curl -s http://127.0.0.1:8080/ | head -5
kill %1
rm -f data/test.db
```

Expected: Status endpoint JSON döner (`connected: false`), settings endpoint tüm varsayılanları döner, dashboard HTML döner.

- [ ] **Step 3: Son commit**

```bash
git add -A
git commit -m "chore: entegrasyon doğrulaması tamamlandı"
```
