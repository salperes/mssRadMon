# Sureli Alarm Esikleri Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alarm thresholds trigger only after being continuously exceeded for a configurable duration, with a pending alarm indicator shown on the dashboard.

**Architecture:** Two new config keys for duration (seconds). AlarmManager gains time-tracking state and a `get_pending()` method. WS messages carry pending alarm info. Dashboard banner shows countdown during pending state.

**Tech Stack:** Python/FastAPI, vanilla JS (existing stack)

---

### Task 1: Config Defaults for Duration

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: Add duration defaults**

In `app/config.py`, in the `DEFAULTS` dict, after `"threshold_high_high": "1.0",` (line 9), add:

```python
    "threshold_high_duration": "120",
    "threshold_high_high_duration": "15",
```

- [ ] **Step 2: Verify**

Run: `cd /home/alper/mssRadMon && source .venv/bin/activate && python -c "from app.config import DEFAULTS; assert 'threshold_high_duration' in DEFAULTS; assert 'threshold_high_high_duration' in DEFAULTS; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "feat: config defaults for alarm duration thresholds"
```

---

### Task 2: AlarmManager Duration Logic

**Files:**
- Modify: `app/alarm.py`

- [ ] **Step 1: Add time import**

At the top of `app/alarm.py`, after `from enum import Enum`, add:

```python
import time
```

- [ ] **Step 2: Add state fields to __init__**

In `AlarmManager.__init__`, after `self._buzzer_task: asyncio.Task | None = None` (line 39), add:

```python
        self._exceed_start: float | None = None
        self._exceed_level: AlarmLevel | None = None
```

- [ ] **Step 3: Replace check() method**

Replace the entire `check()` method (lines 56-80) with:

```python
    async def check(self, dose_rate: float) -> AlarmLevel | None:
        """Doz hizini kontrol et. Sure dolunca alarm tetikle."""
        high = float(await self._config.get("threshold_high") or "0.5")
        high_high = float(await self._config.get("threshold_high_high") or "1.0")
        high_dur = float(await self._config.get("threshold_high_duration") or "120")
        high_high_dur = float(await self._config.get("threshold_high_high_duration") or "15")

        # Esik altina dustuyse sayaci sifirla ve temizle
        if dose_rate < high:
            self._exceed_start = None
            self._exceed_level = None
            if self._active_level is not None:
                await self._clear_alarm()
            return None

        # Seviyeyi belirle
        if dose_rate >= high_high:
            new_level = AlarmLevel.HIGH_HIGH
            required_dur = high_high_dur
        else:
            new_level = AlarmLevel.HIGH
            required_dur = high_dur

        now = time.monotonic()

        # Seviye degistiyse sayaci sifirla
        if self._exceed_level != new_level:
            self._exceed_start = now
            self._exceed_level = new_level
            return None

        # Gecen sureyi hesapla
        elapsed = now - self._exceed_start

        # Sure dolmadiysa pending olarak kal
        if elapsed < required_dur:
            return None

        # Zaten ayni seviyede aktif alarm varsa tekrar tetikleme
        if self._active_level == new_level:
            return None

        # Sure doldu — alarm tetikle
        self._active_level = new_level
        await self._trigger_alarm(new_level, dose_rate)
        return new_level
```

- [ ] **Step 4: Add get_pending() method**

After the `check()` method, add:

```python
    def get_pending(self) -> dict:
        """Dashboard icin pending alarm bilgisi dondur."""
        if self._exceed_start is None or self._exceed_level is None:
            return {
                "alarm_pending": False,
                "alarm_pending_level": None,
                "alarm_pending_elapsed": 0,
                "alarm_pending_duration": 0,
            }
        elapsed = time.monotonic() - self._exceed_start
        return {
            "alarm_pending": self._active_level != self._exceed_level,
            "alarm_pending_level": self._exceed_level.value,
            "alarm_pending_elapsed": round(elapsed),
            "alarm_pending_duration": 0,  # placeholder, filled by caller or config
        }
```

Note: `alarm_pending` is True only when threshold is exceeded but alarm hasn't fired yet. Once alarm fires (`_active_level == _exceed_level`), pending becomes False.

- [ ] **Step 5: Add get_pending_with_duration() method**

Replace the `get_pending()` method above with a version that reads config. Actually, since `get_pending()` needs to be sync (called from WS path), we need to cache the durations. Better approach — add an async helper that main.py will call:

After `get_pending()`, add:

```python
    async def get_pending_info(self) -> dict:
        """Async versiyon — config'den sure bilgisini de okur."""
        info = self.get_pending()
        if info["alarm_pending"] and info["alarm_pending_level"]:
            dur_key = f"threshold_{info['alarm_pending_level']}_duration"
            dur = float(await self._config.get(dur_key) or "0")
            info["alarm_pending_duration"] = round(dur)
        return info
```

Remove the plain `get_pending()` method — we only need `get_pending_info()`.

Actually, let's keep it simpler. Just have one async method:

Replace both with a single method after `check()`:

```python
    async def get_pending_info(self) -> dict:
        """Pending alarm bilgisi — dashboard ve WS icin."""
        if self._exceed_start is None or self._exceed_level is None or self._active_level == self._exceed_level:
            return {
                "alarm_pending": False,
                "alarm_pending_level": None,
                "alarm_pending_elapsed": 0,
                "alarm_pending_duration": 0,
            }
        elapsed = time.monotonic() - self._exceed_start
        dur_key = f"threshold_{self._exceed_level.value}_duration"
        duration = float(await self._config.get(dur_key) or "0")
        return {
            "alarm_pending": True,
            "alarm_pending_level": self._exceed_level.value,
            "alarm_pending_elapsed": round(elapsed),
            "alarm_pending_duration": round(duration),
        }
```

- [ ] **Step 6: Verify**

Run: `cd /home/alper/mssRadMon && source .venv/bin/activate && python -c "from app.alarm import AlarmManager; print('OK')"`

- [ ] **Step 7: Commit**

```bash
git add app/alarm.py
git commit -m "feat: duration-based alarm thresholds with pending state"
```

---

### Task 3: WS Message and API — Pending Alarm Info

**Files:**
- Modify: `app/main.py`
- Modify: `app/routers/api.py`

- [ ] **Step 1: Add pending info to WS message in main.py**

In `app/main.py`, in the `on_reading` callback, after line `shift_info = await shift_manager.get_current()` (line 87), add:

```python
            pending_info = await alarm_manager.get_pending_info()
```

Then in the `msg = {` dict (lines 88-96), after the `"shift_active"` line, add:

```python
                "alarm_pending": pending_info["alarm_pending"],
                "alarm_pending_level": pending_info["alarm_pending_level"],
                "alarm_pending_elapsed": pending_info["alarm_pending_elapsed"],
                "alarm_pending_duration": pending_info["alarm_pending_duration"],
```

- [ ] **Step 2: Add pending info to /api/current endpoint**

In `app/routers/api.py`, in the `get_current` function, after `connected = request.app.state.reader.connected` (line 24), add:

```python
    alarm = request.app.state.alarm
    pending = await alarm.get_pending_info()
```

Then in the return dict (when row exists, lines 26-31), add the pending fields. Replace:

```python
    if row:
        return {
            "timestamp": row["timestamp"],
            "dose_rate": row["dose_rate"],
            "cumulative_dose": row["cumulative_dose"],
            "connected": connected,
        }
    return {"timestamp": None, "dose_rate": None, "cumulative_dose": None, "connected": connected}
```

With:

```python
    if row:
        return {
            "timestamp": row["timestamp"],
            "dose_rate": row["dose_rate"],
            "cumulative_dose": row["cumulative_dose"],
            "connected": connected,
            **pending,
        }
    return {"timestamp": None, "dose_rate": None, "cumulative_dose": None, "connected": connected, **pending}
```

- [ ] **Step 3: Commit**

```bash
git add app/main.py app/routers/api.py
git commit -m "feat: pending alarm info in WS messages and /api/current"
```

---

### Task 4: Dashboard — Pending Alarm Banner

**Files:**
- Modify: `app/static/js/dashboard.js`

- [ ] **Step 1: Add updatePendingAlarm function**

After the `updateShift` function (after line 129), add:

```javascript
function updatePendingAlarm(pending, level, elapsed, duration) {
    if (pending) {
        const levelText = level === "high_high" ? "KRITIK eşik aşıldı" : "HIGH eşiği aşıldı";
        alarmBanner.className = "alarm-banner active " + (level === "high_high" ? "high_high" : "high");
        alarmLevel.textContent = level === "high_high" ? "ÖN UYARI" : "ÖN UYARI";
        alarmMsg.textContent = `${levelText} — ${elapsed}/${duration} sn`;
    }
}
```

- [ ] **Step 2: Call updatePendingAlarm in WS onmessage**

In the WS `onmessage` handler, after the `updateShift(...)` line (line 249), add:

```javascript
            if (msg.alarm_pending) {
                updatePendingAlarm(true, msg.alarm_pending_level, msg.alarm_pending_elapsed, msg.alarm_pending_duration);
            } else if (!msg.alarm_pending) {
                // Pending bitti — banner'i gizle (gercek alarm varsa alarms endpoint gosterir)
                alarmBanner.className = "alarm-banner";
            }
```

- [ ] **Step 3: Handle pending in loadInitial**

In `loadInitial`, after `updateConnection(current.connected);` (line 208), add:

```javascript
        if (current.alarm_pending) {
            updatePendingAlarm(true, current.alarm_pending_level, current.alarm_pending_elapsed, current.alarm_pending_duration);
        }
```

- [ ] **Step 4: Commit**

```bash
git add app/static/js/dashboard.js
git commit -m "feat: dashboard pending alarm banner with countdown"
```

---

### Task 5: Admin Panel — Duration Inputs

**Files:**
- Modify: `app/templates/admin.html`
- Modify: `app/static/js/admin.js`

- [ ] **Step 1: Add duration inputs to admin.html**

In `app/templates/admin.html`, in the Alarm & GPIO section, replace the threshold grid (lines 61-70):

```html
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
```

With:

```html
                <div class="dashboard-grid">
                    <div class="form-group">
                        <label for="threshold_high">High Eşiği (µSv/h)</label>
                        <input type="number" id="threshold_high" step="0.01" min="0">
                    </div>
                    <div class="form-group">
                        <label for="threshold_high_duration">High Süresi (sn)</label>
                        <input type="number" id="threshold_high_duration" min="0" step="1">
                    </div>
                    <div class="form-group">
                        <label for="threshold_high_high">High-High Eşiği (µSv/h)</label>
                        <input type="number" id="threshold_high_high" step="0.01" min="0">
                    </div>
                    <div class="form-group">
                        <label for="threshold_high_high_duration">High-High Süresi (sn)</label>
                        <input type="number" id="threshold_high_high_duration" min="0" step="1">
                    </div>
                </div>
```

- [ ] **Step 2: Add duration fields to FIELDS array in admin.js**

In `app/static/js/admin.js`, in the `FIELDS` array (line 34), after `"threshold_high_high",`, add:

```javascript
    "threshold_high_duration", "threshold_high_high_duration",
```

The line should become:
```javascript
    "sampling_interval", "threshold_high", "threshold_high_high",
    "threshold_high_duration", "threshold_high_high_duration",
```

- [ ] **Step 3: Commit**

```bash
git add app/templates/admin.html app/static/js/admin.js
git commit -m "feat: admin panel alarm duration inputs"
```

---

### Task 6: Verification

- [ ] **Step 1: Verify app starts**

Run: `cd /home/alper/mssRadMon && source .venv/bin/activate && python -c "from app.main import create_app; print('OK')"`

- [ ] **Step 2: Verify all imports**

Run: `cd /home/alper/mssRadMon && source .venv/bin/activate && python -c "from app.alarm import AlarmManager; from app.routers.api import router; print('OK')"`
