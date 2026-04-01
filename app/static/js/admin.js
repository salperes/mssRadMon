"use strict";

// --- Sidebar Navigation ---

const sidebarLinks = document.querySelectorAll(".sidebar-link");
const sections = document.querySelectorAll(".admin-section");

function showSection(name) {
    sections.forEach(s => s.classList.remove("active"));
    sidebarLinks.forEach(l => l.classList.remove("active"));
    const target = document.getElementById("sec-" + name);
    const link = document.querySelector(`.sidebar-link[data-section="${name}"]`);
    if (target) target.classList.add("active");
    if (link) link.classList.add("active");
    // URL hash update (geri tuşu desteği)
    history.replaceState(null, "", "#" + name);
}

sidebarLinks.forEach(link => {
    link.addEventListener("click", (e) => {
        e.preventDefault();
        showSection(link.dataset.section);
    });
});

// Hash'ten bölüm aç
const initSection = location.hash.replace("#", "") || "sampling";
showSection(initSection);

// --- Settings ---

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
        console.error("Ayarlar yuklenemedi:", e);
    }
}

async function saveSettings(msgEl) {
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
        if (res.ok && msgEl) {
            msgEl.classList.add("show");
            setTimeout(() => msgEl.classList.remove("show"), 3000);
        }
    } catch (e) {
        console.error("Ayarlar kaydedilemedi:", e);
    }
}

// Ana kaydet butonu (Örnekleme bölümündeki)
document.getElementById("saveBtn").addEventListener("click", () => {
    saveSettings(document.getElementById("saveMsg"));
});

// Her bölümdeki kaydet butonları
document.querySelectorAll(".save-section-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        const msg = btn.parentElement.querySelector(".save-section-msg");
        saveSettings(msg);
    });
});

// --- Test Email ---

document.getElementById("testEmailBtn").addEventListener("click", async () => {
    const msgEl = document.getElementById("testEmailMsg");
    msgEl.textContent = "Gönderiliyor...";
    msgEl.style.color = "var(--text-dim)";
    // Önce ayarları kaydet, sonra test gönder
    await saveSettings(null);
    try {
        const res = await fetch("/api/test-email", { method: "POST" });
        const data = await res.json();
        msgEl.textContent = data.message;
        msgEl.style.color = data.ok ? "var(--green)" : "var(--red)";
    } catch (e) {
        msgEl.textContent = "Gönderme hatası";
        msgEl.style.color = "var(--red)";
    }
});

// --- Alarm History ---

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
            const levelStr = a.level === "high_high" ? "KRITIK" : "UYARI";
            const row = document.createElement("tr");
            row.innerHTML = `<td>${timeStr}</td><td>${levelStr}</td><td>${a.dose_rate.toFixed(3)} uSv/h</td><td>${a.action_taken}</td>`;
            tbody.appendChild(row);
        });
    } catch (e) {
        console.error("Alarm gecmisi yuklenemedi:", e);
    }
}

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
        wifiStatusEl.innerHTML = `${dot}<strong>${modeText}</strong> &mdash; SSID: <strong>${s.ssid || "\u2014"}</strong> &mdash; IP: <strong>${s.ip || "\u2014"}</strong>`;
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
            item.innerHTML = `<span>${n.ssid}</span><span style="color:${signal}">${n.signal}%${n.security ? " &#x1f512;" : ""}</span>`;
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

async function loadSavedNetworks() {
    const el = document.getElementById("savedNetworks");
    try {
        const res = await fetch("/api/wifi/saved");
        const nets = await res.json();
        if (nets.length === 0) {
            el.innerHTML = "Kayitli ag yok.";
            return;
        }
        el.innerHTML = "";
        const list = document.createElement("div");
        list.style.cssText = "display:flex;flex-direction:column;gap:0.25rem;";
        nets.forEach(n => {
            const item = document.createElement("div");
            item.style.cssText = "display:flex;justify-content:space-between;align-items:center;padding:0.4rem 0.6rem;background:var(--bg);border-radius:4px;font-size:0.85rem;";
            const delBtn = document.createElement("button");
            delBtn.textContent = "Sil";
            delBtn.style.cssText = "background:none;border:1px solid var(--red);color:var(--red);border-radius:4px;padding:0.15rem 0.5rem;cursor:pointer;font-size:0.75rem;";
            delBtn.addEventListener("click", async () => {
                await fetch(`/api/wifi/saved/${encodeURIComponent(n.ssid)}`, { method: "DELETE" });
                loadSavedNetworks();
            });
            item.innerHTML = `<span>${n.ssid} ${n.has_password ? "&#x1f512;" : ""}</span>`;
            item.appendChild(delBtn);
            list.appendChild(item);
        });
        el.appendChild(list);
    } catch (e) {
        el.innerHTML = "Yuklenemedi.";
    }
}

document.getElementById("wifiClientBtn").addEventListener("click", () => {
    clientPanel.style.display = clientPanel.style.display === "none" ? "block" : "none";
    apPanel.style.display = "none";
    if (clientPanel.style.display === "block") { scanNetworks(); loadSavedNetworks(); }
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
        if (data.ok) { setTimeout(loadWifiStatus, 2000); loadSavedNetworks(); }
    } catch (e) {
        msgEl.textContent = "Baglanti hatasi"; msgEl.style.color = "var(--red)";
    }
});

document.getElementById("wifiSaveOnlyBtn").addEventListener("click", async () => {
    const ssid = document.getElementById("wifiSsid").value;
    const pass = document.getElementById("wifiPass").value;
    const msgEl = document.getElementById("wifiClientMsg");
    if (!ssid) { msgEl.textContent = "SSID giriniz"; msgEl.style.color = "var(--red)"; return; }
    try {
        const res = await fetch("/api/wifi/saved", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ssid, password: pass }),
        });
        const data = await res.json();
        msgEl.textContent = data.ok ? "Kaydedildi" : data.message;
        msgEl.style.color = data.ok ? "var(--green)" : "var(--red)";
        if (data.ok) loadSavedNetworks();
    } catch (e) {
        msgEl.textContent = "Kaydetme hatasi"; msgEl.style.color = "var(--red)";
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

// --- Init ---

loadSettings();
loadAlarmHistory();
loadWifiStatus();
