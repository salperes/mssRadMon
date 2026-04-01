# Vardiya Yonetimi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add flexible shift definitions with per-shift cumulative dose tracking, displayed on the dashboard and managed via admin panel.

**Architecture:** Shifts stored as JSON in existing settings table. New `shift_doses` table tracks per-shift dose accumulation. `ShiftManager` class handles shift detection and dose calculation, called on each reading. Dashboard shows active shift dose card + history table; admin panel gets a new Shifts section.

**Tech Stack:** Python/FastAPI, aiosqlite, vanilla JS, Chart.js (existing stack)

---

### Task 1: Database Schema — Add shift_doses Table

**Files:**
- Modify: `app/db.py:4-29` (SCHEMA string)

- [ ] **Step 1: Add shift_doses table to SCHEMA**

In `app/db.py`, add the following to the end of the `SCHEMA` string (before the closing `"""`):

```python
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
```

- [ ] **Step 2: Add shifts default to config**

In `app/config.py`, add to `DEFAULTS` dict:

```python
"shifts": "[]",
```

- [ ] **Step 3: Verify app starts**

Run: `cd /home/alper/mssRadMon && python -c "from app.db import SCHEMA; print('OK')" && python -c "from app.config import DEFAULTS; assert 'shifts' in DEFAULTS; print('OK')"`
Expected: Two "OK" lines

- [ ] **Step 4: Commit**

```bash
git add app/db.py app/config.py
git commit -m "feat: shift_doses table schema and shifts config default"
```

---

### Task 2: ShiftManager Backend Logic

**Files:**
- Create: `app/shift.py`

- [ ] **Step 1: Create app/shift.py with ShiftManager class**

```python
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

    async def check(self, cumulative_dose: float):
        """Her okumada cagrilir. Aktif vardiyayi belirler, dozu gunceller."""
        now = datetime.now()
        shifts = await self._get_shifts()

        if not shifts:
            self._last_cumulative = cumulative_dose
            self._active_shift_id = None
            return

        active = self._find_active_shift(shifts, now)
        today = now.strftime("%Y-%m-%d")

        # Onceki aktif vardiya bittiyse kapat
        if self._active_shift_id and (active is None or active["id"] != self._active_shift_id):
            await self._db.execute(
                "UPDATE shift_doses SET completed = 1 WHERE shift_id = ? AND date = ? AND completed = 0",
                (self._active_shift_id, today),
            )
            self._active_shift_id = None

        if active is None:
            self._last_cumulative = cumulative_dose
            return

        self._active_shift_id = active["id"]

        # Bu vardiya icin bugunun kaydini bul veya olustur
        row = await self._db.fetch_one(
            "SELECT id, dose FROM shift_doses WHERE shift_id = ? AND date = ? AND completed = 0",
            (active["id"], today),
        )

        if row is None:
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

        today = now.strftime("%Y-%m-%d")
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
        """Uygulama baslarken completed=0 olan eski kayitlari kapat."""
        today = datetime.now().strftime("%Y-%m-%d")
        await self._db.execute(
            "UPDATE shift_doses SET completed = 1 WHERE completed = 0 AND date < ?",
            (today,),
        )
```

- [ ] **Step 2: Verify import**

Run: `cd /home/alper/mssRadMon && python -c "from app.shift import ShiftManager; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add app/shift.py
git commit -m "feat: ShiftManager — aktif vardiya tespiti ve doz takibi"
```

---

### Task 3: Integrate ShiftManager into main.py

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add import**

Add after the existing imports (line 17):

```python
from app.shift import ShiftManager
```

- [ ] **Step 2: Create ShiftManager in lifespan, after alarm_manager**

After line `alarm_manager = AlarmManager(db=db, config=config)` and `await alarm_manager.init()`, add:

```python
        shift_manager = ShiftManager(db=db, config=config)
        await shift_manager.close_stale()
```

- [ ] **Step 3: Assign to app state**

After `app.state.remote_log = remote_log`, add:

```python
        app.state.shift_manager = shift_manager
```

- [ ] **Step 4: Add shift check to on_reading callback**

After `await alarm_manager.check(reading.dose_rate)` (line 78), add:

```python
            # Vardiya doz takibi
            await shift_manager.check(reading.cumulative_dose)
```

- [ ] **Step 5: Add shift data to WebSocket message**

Replace the `msg = {` block (lines 80-85) with:

```python
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
```

- [ ] **Step 6: Commit**

```bash
git add app/main.py
git commit -m "feat: ShiftManager entegrasyonu — on_reading ve WS mesajı"
```

---

### Task 4: API Endpoints for Shift Data

**Files:**
- Modify: `app/routers/api.py`

- [ ] **Step 1: Add shift/current endpoint**

Add at the end of `api.py`:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add app/routers/api.py
git commit -m "feat: /api/shift/current ve /api/shift/history endpoint'leri"
```

---

### Task 5: Dashboard Frontend — Shift Dose Card

**Files:**
- Modify: `app/templates/dashboard.html`
- Modify: `app/static/js/dashboard.js`
- Modify: `app/static/css/style.css`

- [ ] **Step 1: Add shift dose card to dashboard.html**

In `dashboard.html`, change the `dashboard-grid` div (lines 13-28) to include a third card. Replace:

```html
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
```

With:

```html
<div class="dashboard-grid dashboard-grid-3">
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
    <div class="card">
        <div class="card-title">Vardiya Dozu</div>
        <div>
            <span class="shift-name" id="shiftName">—</span>
        </div>
        <div>
            <span class="daily-dose-value" id="shiftDose">—</span>
            <span class="dose-rate-unit">µSv</span>
        </div>
    </div>
</div>
```

- [ ] **Step 2: Add shift history table after the chart card**

In `dashboard.html`, after the chart card's closing `</div>` (line 48), add:

```html
<div class="card">
    <div class="card-title">Vardiya Doz Geçmişi</div>
    <table class="alarm-table" id="shiftHistoryTable">
        <thead>
            <tr><th>Tarih</th><th>Vardiya</th><th>Saat</th><th>Doz (µSv)</th></tr>
        </thead>
        <tbody id="shiftHistoryBody">
        </tbody>
    </table>
</div>
```

- [ ] **Step 3: Add CSS for 3-column grid**

In `app/static/css/style.css`, after the `.dashboard-grid` block (after line 75), add:

```css
.dashboard-grid-3 {
    grid-template-columns: 1fr 1fr 1fr;
}
@media (max-width: 600px) {
    .dashboard-grid-3 { grid-template-columns: 1fr; }
}
```

- [ ] **Step 4: Add shift name style to CSS**

In `app/static/css/style.css`, after the `.daily-dose-value` rule (line 110), add:

```css
.shift-name { font-size: 0.9rem; color: var(--accent); font-weight: 600; }
```

- [ ] **Step 5: Commit**

```bash
git add app/templates/dashboard.html app/static/css/style.css
git commit -m "feat: dashboard vardiya dozu kartı ve geçmiş tablosu HTML/CSS"
```

---

### Task 6: Dashboard JavaScript — Shift Data

**Files:**
- Modify: `app/static/js/dashboard.js`

- [ ] **Step 1: Add element references**

After the `const chartRangeEl` line (line 13), add:

```javascript
const shiftNameEl = document.getElementById("shiftName");
const shiftDoseEl = document.getElementById("shiftDose");
const shiftHistoryBody = document.getElementById("shiftHistoryBody");
```

- [ ] **Step 2: Add updateShift function**

After the `updateConnection` function (after line 116), add:

```javascript
function updateShift(active, name, dose) {
    if (active && name) {
        shiftNameEl.textContent = name;
        shiftDoseEl.textContent = dose.toFixed(3);
    } else {
        shiftNameEl.textContent = "Vardiya dışı";
        shiftDoseEl.textContent = "—";
    }
}
```

- [ ] **Step 3: Add loadShiftHistory function**

After the `updateShift` function, add:

```javascript
async function loadShiftHistory() {
    try {
        const res = await fetch("/api/shift/history?days=7");
        const rows = await res.json();
        shiftHistoryBody.innerHTML = "";
        if (rows.length === 0) {
            shiftHistoryBody.innerHTML = '<tr><td colspan="4" style="color:var(--text-dim)">Vardiya kaydı yok</td></tr>';
            return;
        }
        rows.forEach(r => {
            const tr = document.createElement("tr");
            const dateStr = new Date(r.date).toLocaleDateString("tr-TR");
            tr.innerHTML = `<td>${dateStr}</td><td>${r.shift_name}</td><td>${r.start_time}–${r.end_time}</td><td>${r.dose.toFixed(3)}</td>`;
            shiftHistoryBody.appendChild(tr);
        });
    } catch (e) {
        console.error("Vardiya geçmişi yüklenemedi:", e);
    }
}
```

- [ ] **Step 4: Load shift data in loadInitial**

Inside the `loadInitial` function, after the daily dose block (`dailyDoseEl.textContent = daily.daily_dose.toFixed(3);`), add:

```javascript
        const shiftRes = await fetch("/api/shift/current");
        const shift = await shiftRes.json();
        updateShift(shift.active, shift.shift_name, shift.shift_dose);

        await loadShiftHistory();
```

- [ ] **Step 5: Handle shift in WebSocket message**

Inside the `ws.onmessage` handler, after the daily dose fetch block, add:

```javascript
            updateShift(msg.shift_active, msg.shift_name, msg.shift_dose);
```

- [ ] **Step 6: Commit**

```bash
git add app/static/js/dashboard.js
git commit -m "feat: dashboard JS — vardiya dozu güncelleme ve geçmiş tablosu"
```

---

### Task 7: Admin Panel — Shifts Section HTML

**Files:**
- Modify: `app/templates/admin.html`

- [ ] **Step 1: Add sidebar link**

In `admin.html`, after the WiFi sidebar link (line 14), add:

```html
            <a href="#" class="sidebar-link" data-section="shifts">Vardiyalar</a>
```

- [ ] **Step 2: Add shifts section**

Before the `<!-- Alarm Geçmişi -->` comment (line 252), add:

```html
        <!-- Vardiyalar -->
        <section class="admin-section" id="sec-shifts">
            <h2 class="section-title">Vardiya Ayarları</h2>
            <div id="shiftList"></div>
            <div class="card">
                <div class="card-title">Yeni Vardiya Ekle</div>
                <div class="form-group">
                    <label for="newShiftName">Vardiya Adı</label>
                    <input type="text" id="newShiftName" placeholder="Vardiya 1">
                </div>
                <div class="dashboard-grid">
                    <div class="form-group">
                        <label for="newShiftStart">Başlangıç Saati</label>
                        <input type="time" id="newShiftStart" value="08:00">
                    </div>
                    <div class="form-group">
                        <label for="newShiftEnd">Bitiş Saati</label>
                        <input type="time" id="newShiftEnd" value="16:00">
                    </div>
                </div>
                <div class="form-group">
                    <label>Aktif Günler</label>
                    <div class="shift-days-row" id="newShiftDays">
                        <label class="shift-day-check"><input type="checkbox" value="1" checked> Pzt</label>
                        <label class="shift-day-check"><input type="checkbox" value="2" checked> Sal</label>
                        <label class="shift-day-check"><input type="checkbox" value="3" checked> Çar</label>
                        <label class="shift-day-check"><input type="checkbox" value="4" checked> Per</label>
                        <label class="shift-day-check"><input type="checkbox" value="5" checked> Cum</label>
                        <label class="shift-day-check"><input type="checkbox" value="6"> Cmt</label>
                        <label class="shift-day-check"><input type="checkbox" value="7"> Paz</label>
                    </div>
                </div>
                <button class="btn" id="addShiftBtn">Vardiya Ekle</button>
            </div>
        </section>
```

- [ ] **Step 3: Add CSS for shift day checkboxes**

In `app/static/css/style.css`, at the end of the file, add:

```css
/* Shift day checkboxes */
.shift-days-row {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
}
.shift-day-check {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.85rem;
    color: var(--text);
    cursor: pointer;
}
.shift-day-check input[type="checkbox"] {
    width: auto;
    accent-color: var(--accent);
}
.shift-card {
    background: var(--card);
    border-radius: 12px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5rem;
}
.shift-card-info { flex: 1; min-width: 200px; }
.shift-card-name { font-weight: 600; font-size: 1rem; margin-bottom: 0.25rem; }
.shift-card-detail { font-size: 0.85rem; color: var(--text-dim); }
.shift-card-days { font-size: 0.8rem; color: var(--accent); margin-top: 0.2rem; }
```

- [ ] **Step 4: Commit**

```bash
git add app/templates/admin.html app/static/css/style.css
git commit -m "feat: admin panel vardiyalar bölümü HTML/CSS"
```

---

### Task 8: Admin JavaScript — Shift CRUD

**Files:**
- Modify: `app/static/js/admin.js`

- [ ] **Step 1: Add shift management code**

At the end of `app/static/js/admin.js`, before the `// --- Init ---` section, add:

```javascript
// --- Shifts ---

const DAY_NAMES = { 1: "Pzt", 2: "Sal", 3: "Çar", 4: "Per", 5: "Cum", 6: "Cmt", 7: "Paz" };
let currentShifts = [];

function generateShiftId() {
    return "s" + Date.now().toString(36);
}

function renderShifts() {
    const container = document.getElementById("shiftList");
    container.innerHTML = "";
    if (currentShifts.length === 0) {
        container.innerHTML = '<div class="card" style="color:var(--text-dim);text-align:center;padding:2rem;">Tanımlı vardiya yok</div>';
        return;
    }
    currentShifts.forEach((shift, idx) => {
        const dayStr = shift.days.map(d => DAY_NAMES[d] || d).join(", ");
        const card = document.createElement("div");
        card.className = "shift-card";
        card.innerHTML = `
            <div class="shift-card-info">
                <div class="shift-card-name">${shift.name}</div>
                <div class="shift-card-detail">${shift.start} – ${shift.end}</div>
                <div class="shift-card-days">${dayStr}</div>
            </div>
        `;
        const delBtn = document.createElement("button");
        delBtn.textContent = "Sil";
        delBtn.className = "btn";
        delBtn.style.cssText = "background:none;border:1px solid var(--red);color:var(--red);padding:0.3rem 0.75rem;font-size:0.8rem;";
        delBtn.addEventListener("click", () => {
            currentShifts.splice(idx, 1);
            renderShifts();
            saveShifts();
        });
        card.appendChild(delBtn);
        container.appendChild(card);
    });
}

async function loadShifts() {
    try {
        const res = await fetch("/api/settings");
        const settings = await res.json();
        const raw = settings.shifts || "[]";
        currentShifts = JSON.parse(raw);
    } catch (e) {
        currentShifts = [];
    }
    renderShifts();
}

async function saveShifts() {
    try {
        await fetch("/api/settings", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ shifts: JSON.stringify(currentShifts) }),
        });
    } catch (e) {
        console.error("Vardiyalar kaydedilemedi:", e);
    }
}

document.getElementById("addShiftBtn").addEventListener("click", () => {
    const name = document.getElementById("newShiftName").value.trim();
    const start = document.getElementById("newShiftStart").value;
    const end = document.getElementById("newShiftEnd").value;
    if (!name || !start || !end) return;

    const dayCheckboxes = document.querySelectorAll("#newShiftDays input[type='checkbox']");
    const days = [];
    dayCheckboxes.forEach(cb => { if (cb.checked) days.push(parseInt(cb.value)); });
    if (days.length === 0) return;

    currentShifts.push({
        id: generateShiftId(),
        name: name,
        start: start,
        end: end,
        days: days,
    });

    renderShifts();
    saveShifts();

    // Formu temizle
    document.getElementById("newShiftName").value = "";
    document.getElementById("newShiftStart").value = "08:00";
    document.getElementById("newShiftEnd").value = "16:00";
});
```

- [ ] **Step 2: Add loadShifts to init**

In the `// --- Init ---` section at the bottom of admin.js, after `loadWifiStatus();`, add:

```javascript
loadShifts();
```

- [ ] **Step 3: Commit**

```bash
git add app/static/js/admin.js
git commit -m "feat: admin JS — vardiya ekleme, silme ve kaydetme"
```

---

### Task 9: Integration Verification

**Files:** (no new changes, just verification)

- [ ] **Step 1: Verify app starts without errors**

Run: `cd /home/alper/mssRadMon && timeout 5 python -c "import asyncio; from app.main import create_app; print('App created OK')" || true`
Expected: "App created OK"

- [ ] **Step 2: Verify all imports work**

Run: `cd /home/alper/mssRadMon && python -c "from app.shift import ShiftManager; from app.routers.api import router; print('All imports OK')"`
Expected: "All imports OK"

- [ ] **Step 3: Quick manual smoke test description**

Open browser to `http://<device-ip>:8090`:
- Dashboard should show three cards (Dose Rate, Daily Dose, Shift Dose)
- Shift Dose card should show "Vardiya disi" if no shifts defined
- Shift history table should show "Vardiya kaydi yok"
- Navigate to Admin > Vardiyalar
- Add a shift: name="Test", start=current hour, end=current hour+1, days=today
- Dashboard should start showing shift name and accumulating dose

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: integration fixes for shift management"
```
