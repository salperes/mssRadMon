"use strict";

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
