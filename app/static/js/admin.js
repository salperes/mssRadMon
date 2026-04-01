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

// --- WiFi ---

const wifiStatusEl = document.getElementById("wifiStatus");
const clientPanel = document.getElementById("clientPanel");
const apPanel = document.getElementById("apPanel");
const wifiNetworksEl = document.getElementById("wifiNetworks");

async function loadWifiStatus() {
    try {
        const res = await fetch("/api/wifi/status");
        const s = await res.json();
        const modeText = s.mode === "ap" ? "AP" : s.mode === "client" ? "Client" : "Bilinmiyor";
        const dot = s.mode !== "unknown"
            ? '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--green);margin-right:0.4rem;"></span>'
            : '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--red);margin-right:0.4rem;"></span>';
        wifiStatusEl.innerHTML = `${dot}<strong>${modeText}</strong> &mdash; SSID: <strong>${s.ssid || "—"}</strong> &mdash; IP: <strong>${s.ip || "—"}</strong>`;
    } catch (e) {
        wifiStatusEl.innerHTML = '<span style="color:var(--red)">WiFi durumu alinamadi</span>';
    }
}

async function scanNetworks() {
    wifiNetworksEl.innerHTML = "Taraniyor...";
    try {
        const res = await fetch("/api/wifi/scan");
        const nets = await res.json();
        if (nets.length === 0) {
            wifiNetworksEl.innerHTML = "Ag bulunamadi.";
            return;
        }
        wifiNetworksEl.innerHTML = "";
        const list = document.createElement("div");
        list.style.cssText = "display:flex;flex-direction:column;gap:0.25rem;max-height:200px;overflow-y:auto;";
        nets.forEach(n => {
            const item = document.createElement("div");
            item.style.cssText = "display:flex;justify-content:space-between;align-items:center;padding:0.4rem 0.6rem;background:var(--bg);border-radius:4px;cursor:pointer;font-size:0.85rem;";
            const signal = n.signal >= 70 ? "var(--green)" : n.signal >= 40 ? "var(--yellow)" : "var(--red)";
            item.innerHTML = `<span>${n.ssid}</span><span style="color:${signal}">${n.signal}% ${n.security ? "&#x1f512;" : ""}</span>`;
            item.addEventListener("click", () => {
                document.getElementById("wifiSsid").value = n.ssid;
                document.getElementById("wifiPass").value = "";
                document.getElementById("wifiPass").focus();
            });
            list.appendChild(item);
        });
        wifiNetworksEl.appendChild(list);
    } catch (e) {
        wifiNetworksEl.innerHTML = "Tarama hatasi.";
    }
}

document.getElementById("wifiClientBtn").addEventListener("click", () => {
    clientPanel.style.display = clientPanel.style.display === "none" ? "block" : "none";
    apPanel.style.display = "none";
    if (clientPanel.style.display === "block") scanNetworks();
});

document.getElementById("wifiApBtn").addEventListener("click", () => {
    apPanel.style.display = apPanel.style.display === "none" ? "block" : "none";
    clientPanel.style.display = "none";
});

document.getElementById("wifiConnectBtn").addEventListener("click", async () => {
    const ssid = document.getElementById("wifiSsid").value;
    const pass = document.getElementById("wifiPass").value;
    const msgEl = document.getElementById("wifiClientMsg");
    if (!ssid) { msgEl.textContent = "SSID giriniz"; msgEl.style.color = "var(--red)"; return; }
    msgEl.textContent = "Baglaniyor..."; msgEl.style.color = "var(--text-dim)";
    try {
        const res = await fetch("/api/wifi/connect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ssid, password: pass }),
        });
        const data = await res.json();
        msgEl.textContent = data.message;
        msgEl.style.color = data.ok ? "var(--green)" : "var(--red)";
        if (data.ok) setTimeout(loadWifiStatus, 2000);
    } catch (e) {
        msgEl.textContent = "Baglanti hatasi"; msgEl.style.color = "var(--red)";
    }
});

document.getElementById("apStartBtn").addEventListener("click", async () => {
    const ssid = document.getElementById("apSsid").value;
    const pass = document.getElementById("apPass").value;
    const msgEl = document.getElementById("wifiApMsg");
    msgEl.textContent = "AP baslatiliyor..."; msgEl.style.color = "var(--text-dim)";
    try {
        const res = await fetch("/api/wifi/ap", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ssid, password: pass }),
        });
        const data = await res.json();
        msgEl.textContent = data.message;
        msgEl.style.color = data.ok ? "var(--green)" : "var(--red)";
        if (data.ok) setTimeout(loadWifiStatus, 2000);
    } catch (e) {
        msgEl.textContent = "AP baslatma hatasi"; msgEl.style.color = "var(--red)";
    }
});

loadSettings();
loadAlarmHistory();
loadWifiStatus();
