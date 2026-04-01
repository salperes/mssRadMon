# Daily Reset (UTC+3) & Periyodik Doz Gösterimi — Implementasyon Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Günlük kümülatif dozu UTC+3 (Türkiye) gece yarısında sıfırla; aylık, 3 aylık, 6 aylık ve yıllık doz özetlerini dashboard'daki "Günlük Kümülatif Doz" kartında küçük fontla göster.

**Architecture:** Backend'e `TZ_TR = timezone(timedelta(hours=3))` sabiti ve iki yardımcı fonksiyon (`_period_start_iso`, `_calc_period_dose`) eklenir; yeni `GET /api/period-doses` endpoint'i oluşturulur ve `get_daily_dose` UTC+3'e güncellenir. Frontend; HTML'e 4 yeni span, CSS'e 2 sınıf, JS'e tek bir `loadPeriodDoses()` fonksiyonu ekler.

**Tech Stack:** Python 3.11, FastAPI, aiosqlite, Vanilla JS, pytest-asyncio

---

## Etkilenen Dosyalar

| Dosya | İşlem |
|-------|-------|
| `app/routers/api.py` | Modify — UTC+3 sabiti, `get_daily_dose` düzeltmesi, `_period_start_iso`, `_calc_period_dose`, `/api/period-doses` endpoint |
| `app/templates/dashboard.html` | Modify — periyot span'leri ekleme |
| `app/static/css/style.css` | Modify — `.period-doses`, `.period-dose-row` |
| `app/static/js/dashboard.js` | Modify — `loadPeriodDoses()` fonksiyonu ve çağrıları |
| `tests/test_api.py` | Modify — yeni endpoint ve yardımcı fonksiyon testleri |

---

## Task 1: Backend — UTC+3 sabiti + yardımcı fonksiyonlar + `/api/period-doses`

**Files:**
- Modify: `app/routers/api.py`
- Modify: `tests/test_api.py`

- [ ] **Adım 1: Testleri yaz**

`tests/test_api.py` dosyasına ekle (mevcut importların altına):

```python
from datetime import datetime, timezone, timedelta
from app.db import Database


def test_period_start_iso_day():
    """Günlük başlangıç: bugünün UTC+3 gece yarısı → UTC'ye çevrilmiş."""
    from app.routers.api import _period_start_iso, TZ_TR
    now_local = datetime(2026, 4, 2, 14, 30, 0, tzinfo=TZ_TR)
    result = _period_start_iso(now_local, "day")
    # 2026-04-02 00:00 UTC+3 = 2026-04-01 21:00 UTC
    assert result == "2026-04-01T21:00:00+00:00"


def test_period_start_iso_month():
    from app.routers.api import _period_start_iso, TZ_TR
    now_local = datetime(2026, 4, 15, 10, 0, 0, tzinfo=TZ_TR)
    result = _period_start_iso(now_local, "month")
    # 2026-04-01 00:00 UTC+3 = 2026-03-31 21:00 UTC
    assert result == "2026-03-31T21:00:00+00:00"


def test_period_start_iso_quarter_q2():
    """Nisan Q2'de (Nis-Haz), başlangıç Nisan 1."""
    from app.routers.api import _period_start_iso, TZ_TR
    now_local = datetime(2026, 5, 20, 10, 0, 0, tzinfo=TZ_TR)
    result = _period_start_iso(now_local, "quarter")
    # 2026-04-01 00:00 UTC+3 = 2026-03-31 21:00 UTC
    assert result == "2026-03-31T21:00:00+00:00"


def test_period_start_iso_quarter_q1():
    """Ocak Q1'de (Oca-Mar), başlangıç Ocak 1."""
    from app.routers.api import _period_start_iso, TZ_TR
    now_local = datetime(2026, 2, 10, 10, 0, 0, tzinfo=TZ_TR)
    result = _period_start_iso(now_local, "quarter")
    # 2026-01-01 00:00 UTC+3 = 2025-12-31 21:00 UTC
    assert result == "2025-12-31T21:00:00+00:00"


def test_period_start_iso_half_year_h2():
    """Temmuz–Aralık H2, başlangıç Temmuz 1."""
    from app.routers.api import _period_start_iso, TZ_TR
    now_local = datetime(2026, 9, 1, 10, 0, 0, tzinfo=TZ_TR)
    result = _period_start_iso(now_local, "half_year")
    # 2026-07-01 00:00 UTC+3 = 2026-06-30 21:00 UTC
    assert result == "2026-06-30T21:00:00+00:00"


def test_period_start_iso_year():
    from app.routers.api import _period_start_iso, TZ_TR
    now_local = datetime(2026, 4, 2, 10, 0, 0, tzinfo=TZ_TR)
    result = _period_start_iso(now_local, "year")
    # 2026-01-01 00:00 UTC+3 = 2025-12-31 21:00 UTC
    assert result == "2025-12-31T21:00:00+00:00"


@pytest.mark.asyncio
async def test_calc_period_dose_empty(test_db_path):
    """Veri yoksa 0.0 döndürmeli."""
    from app.routers.api import _calc_period_dose
    db = Database(test_db_path)
    await db.init()
    result = await _calc_period_dose(db, "2026-01-01T00:00:00+00:00")
    assert result == 0.0
    await db.close()


@pytest.mark.asyncio
async def test_calc_period_dose_with_data(test_db_path):
    """İlk ve son cumulative_dose farkını hesaplamalı."""
    from app.routers.api import _calc_period_dose
    db = Database(test_db_path)
    await db.init()
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-04-01T22:00:00+00:00", 0.10, 100.0),
    )
    await db.execute(
        "INSERT INTO readings (timestamp, dose_rate, cumulative_dose) VALUES (?, ?, ?)",
        ("2026-04-02T08:00:00+00:00", 0.12, 115.5),
    )
    result = await _calc_period_dose(db, "2026-04-01T21:00:00+00:00")
    assert result == 15.5
    await db.close()


@pytest.mark.asyncio
async def test_get_period_doses_returns_all_keys(seeded_db):
    """Endpoint tüm periyot anahtarlarını döndürmeli."""
    from app.routers.api import get_period_doses
    db, config = seeded_db
    request = MagicMock()
    request.app.state.db = db
    result = await get_period_doses(request)
    assert set(result.keys()) == {"daily", "monthly", "quarterly", "half_yearly", "yearly"}
    for v in result.values():
        assert isinstance(v, float)
```

- [ ] **Adım 2: Testlerin başarısız olduğunu doğrula**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest tests/test_api.py::test_period_start_iso_day tests/test_api.py::test_calc_period_dose_empty tests/test_api.py::test_get_period_doses_returns_all_keys -v 2>&1 | tail -20
```

Beklenen: `ERROR` veya `FAILED` (fonksiyon yok)

- [ ] **Adım 3: `api.py` implementasyonunu yaz**

`app/routers/api.py` dosyasının başındaki importları şu şekilde güncelle:

```python
"""REST API endpointleri."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request

from app.__version__ import __version__

router = APIRouter(prefix="/api", tags=["api"])

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
```

Ardından `get_daily_dose` endpoint'ini UTC+3'e göre güncelle:

```python
@router.get("/daily-dose")
async def get_daily_dose(request: Request):
    """Bugünkü toplam kümülatif doz farkını döndür (UTC+3 gece yarısından itibaren)."""
    db = request.app.state.db
    now_local = datetime.now(TZ_TR)
    today_start = _period_start_iso(now_local, "day")

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

    return {"date": now_local.strftime("%Y-%m-%d"), "daily_dose": daily}
```

Ve yeni endpoint'i dosyanın sonuna ekle:

```python
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
```

- [ ] **Adım 4: Testlerin geçtiğini doğrula**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest tests/test_api.py -v 2>&1 | tail -30
```

Beklenen: tüm testler `PASSED`

- [ ] **Adım 5: Commit**

```bash
cd /home/mssadmin/mssRadMon && git add app/routers/api.py tests/test_api.py && git commit -m "feat: period-doses endpoint ve UTC+3 günlük doz sıfırlama"
```

---

## Task 2: Frontend HTML — periyot satırları

**Files:**
- Modify: `app/templates/dashboard.html`

- [ ] **Adım 1: "Günlük Kümülatif Doz" kartını güncelle**

`dashboard.html` içindeki mevcut ikinci kart bloğunu bul ve güncelle:

Mevcut:
```html
    <div class="card">
        <div class="card-title">Günlük Kümülatif Doz</div>
        <div>
            <span class="daily-dose-value" id="dailyDose">—</span>
            <span class="dose-rate-unit">µSv</span>
        </div>
    </div>
```

Yeni hali:
```html
    <div class="card">
        <div class="card-title">Günlük Kümülatif Doz</div>
        <div>
            <span class="daily-dose-value" id="dailyDose">—</span>
            <span class="dose-rate-unit">µSv</span>
        </div>
        <div class="period-doses">
            <div class="period-dose-row">
                <span class="period-label">Aylık</span>
                <span id="monthlyDose">—</span> µSv
            </div>
            <div class="period-dose-row">
                <span class="period-label">3 Aylık</span>
                <span id="quarterlyDose">—</span> µSv
            </div>
            <div class="period-dose-row">
                <span class="period-label">6 Aylık</span>
                <span id="halfYearlyDose">—</span> µSv
            </div>
            <div class="period-dose-row">
                <span class="period-label">Yıllık</span>
                <span id="yearlyDose">—</span> µSv
            </div>
        </div>
    </div>
```

- [ ] **Adım 2: Commit**

```bash
cd /home/mssadmin/mssRadMon && git add app/templates/dashboard.html && git commit -m "feat: günlük doz kartına periyot satırları ekle"
```

---

## Task 3: Frontend CSS — period-doses sınıfları

**Files:**
- Modify: `app/static/css/style.css`

- [ ] **Adım 1: CSS sınıflarını ekle**

`style.css` dosyasının sonuna ekle (`.shift-card-days` bloğunun hemen altına):

```css
/* Period doses */
.period-doses {
    margin-top: 0.75rem;
    padding-top: 0.6rem;
    border-top: 1px solid var(--border);
}
.period-dose-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-size: 0.78rem;
    color: var(--text-dim);
    padding: 0.1rem 0;
    font-variant-numeric: tabular-nums;
}
.period-label {
    font-weight: 500;
}
```

- [ ] **Adım 2: Commit**

```bash
cd /home/mssadmin/mssRadMon && git add app/static/css/style.css && git commit -m "feat: period-doses CSS sınıfları"
```

---

## Task 4: Frontend JS — loadPeriodDoses fonksiyonu

**Files:**
- Modify: `app/static/js/dashboard.js`

- [ ] **Adım 1: Yeni element referanslarını ekle**

`dashboard.js` dosyasının başındaki element tanımlamalarının hemen altına (örneğin `shiftHistoryBody` satırından sonra) ekle:

```js
const monthlyDoseEl = document.getElementById("monthlyDose");
const quarterlyDoseEl = document.getElementById("quarterlyDose");
const halfYearlyDoseEl = document.getElementById("halfYearlyDose");
const yearlyDoseEl = document.getElementById("yearlyDose");
```

- [ ] **Adım 2: `loadPeriodDoses` fonksiyonunu ekle**

`loadShiftHistory` fonksiyonundan hemen önce ekle:

```js
async function loadPeriodDoses() {
    try {
        const res = await fetch("/api/period-doses");
        const d = await res.json();
        dailyDoseEl.textContent = d.daily.toFixed(3);
        monthlyDoseEl.textContent = d.monthly.toFixed(3);
        quarterlyDoseEl.textContent = d.quarterly.toFixed(3);
        halfYearlyDoseEl.textContent = d.half_yearly.toFixed(3);
        yearlyDoseEl.textContent = d.yearly.toFixed(3);
    } catch (e) {
        console.error("Periyot dozları yüklenemedi:", e);
    }
}
```

- [ ] **Adım 3: `loadInitial` içindeki `/api/daily-dose` çağrısını değiştir**

`loadInitial` fonksiyonunda mevcut daily-dose fetch bloğunu bul ve `loadPeriodDoses()` çağrısıyla değiştir:

Mevcut (kaldır):
```js
        const dailyRes = await fetch("/api/daily-dose");
        const daily = await dailyRes.json();
        dailyDoseEl.textContent = daily.daily_dose.toFixed(3);
```

Yeni (yerine koy):
```js
        await loadPeriodDoses();
```

- [ ] **Adım 4: WS message handler'ını güncelle**

`ws.onmessage` içindeki mevcut daily-dose fetch bloğunu bul ve değiştir:

Mevcut (kaldır):
```js
            fetch("/api/daily-dose")
                .then(r => r.json())
                .then(d => { dailyDoseEl.textContent = d.daily_dose.toFixed(3); });
```

Yeni (yerine koy):
```js
            loadPeriodDoses();
```

- [ ] **Adım 5: 60 saniyelik periyodik yenileme ekle**

Mevcut `setInterval` bloklarının ardına (dosyanın alt kısmına, `loadInitial()` çağrısından önce) ekle:

```js
setInterval(loadPeriodDoses, 60000);
```

- [ ] **Adım 6: Commit**

```bash
cd /home/mssadmin/mssRadMon && git add app/static/js/dashboard.js && git commit -m "feat: period-doses JS entegrasyonu"
```

---

## Task 5: Uçtan uca doğrulama

- [ ] **Adım 1: Tüm testleri çalıştır**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && pytest -v 2>&1 | tail -30
```

Beklenen: tüm testler `PASSED`

- [ ] **Adım 2: Uygulamayı başlat ve manuel doğrula**

```bash
cd /home/mssadmin/mssRadMon && source .venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload
```

Tarayıcıda `http://<ip>:8090` aç:
- "Günlük Kümülatif Doz" kartında ana değer görünmeli
- Altında Aylık / 3 Aylık / 6 Aylık / Yıllık satırları küçük fontla görünmeli

`/api/period-doses` endpoint'ini kontrol et:
```bash
curl http://localhost:8090/api/period-doses
```
Beklenen: `{"daily":0.0,"monthly":0.0,"quarterly":0.0,"half_yearly":0.0,"yearly":0.0}` (veri yoksa sıfır)
