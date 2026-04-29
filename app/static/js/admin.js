"use strict";

// --- Sidebar Navigation ---

const sidebarLinks = document.querySelectorAll(".sidebar-link[data-section]");
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
const initSection = location.hash.replace("#", "") || "device";
showSection(initSection);

// --- Settings ---

const FIELDS = [
    "device_name", "device_location", "device_serial",
    "sampling_interval", "calibration_factor",
    "threshold_high", "threshold_high_high", "threshold_critical",
    "threshold_high_duration", "threshold_high_high_duration", "threshold_critical_duration",
    "alarm_high_actions", "alarm_high_high_actions", "alarm_critical_actions",
    "gpio_buzzer_pin", "gpio_light_pin", "gpio_emergency_pin",
    "alarm_buzzer_enabled", "alarm_email_enabled",
    "alarm_email_to", "smtp_host", "smtp_port", "smtp_user", "smtp_pass",
    "remote_log_enabled", "remote_log_url", "remote_log_api_key",
    "msg_service_url", "msg_service_api_key", "msg_service_reply_to",
    "msg_service_mail_enabled", "msg_service_wa_enabled",
    "msg_service_high_mail_to", "msg_service_high_wa_to",
    "msg_service_high_high_mail_to", "msg_service_high_high_wa_to",
];

const TOGGLE_FIELDS = [
    "alarm_buzzer_enabled", "alarm_email_enabled", "remote_log_enabled",
    "msg_service_mail_enabled", "msg_service_wa_enabled",
];

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
        renderRecipients();
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

// --- Email Recipients ---

function renderRecipients() {
    const container = document.getElementById("emailRecipients");
    const hidden = document.getElementById("alarm_email_to");
    const emails = hidden.value ? hidden.value.split(",").map(e => e.trim()).filter(Boolean) : [];
    container.innerHTML = "";
    if (emails.length === 0) {
        container.innerHTML = '<span style="font-size:0.8rem;color:var(--text-dim);">Alıcı yok</span>';
        return;
    }
    emails.forEach(email => {
        const item = document.createElement("div");
        item.style.cssText = "display:flex;justify-content:space-between;align-items:center;padding:0.35rem 0.6rem;background:var(--bg);border-radius:4px;font-size:0.85rem;";
        const del = document.createElement("button");
        del.textContent = "Sil";
        del.style.cssText = "background:none;border:1px solid var(--red);color:var(--red);border-radius:4px;padding:0.1rem 0.4rem;cursor:pointer;font-size:0.75rem;";
        del.addEventListener("click", () => {
            const list = hidden.value.split(",").map(e => e.trim()).filter(e => e !== email);
            hidden.value = list.join(",");
            renderRecipients();
        });
        item.innerHTML = `<span>${email}</span>`;
        item.appendChild(del);
        container.appendChild(item);
    });
}

document.getElementById("addEmailBtn").addEventListener("click", () => {
    const input = document.getElementById("newEmailAddr");
    const addr = input.value.trim();
    if (!addr || !addr.includes("@")) return;
    const hidden = document.getElementById("alarm_email_to");
    const list = hidden.value ? hidden.value.split(",").map(e => e.trim()).filter(Boolean) : [];
    if (!list.includes(addr)) list.push(addr);
    hidden.value = list.join(",");
    input.value = "";
    renderRecipients();
});

document.getElementById("newEmailAddr").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); document.getElementById("addEmailBtn").click(); }
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

// --- Gmail Preset ---

document.getElementById("gmailPresetBtn").addEventListener("click", () => {
    document.getElementById("smtp_host").value = "smtp.gmail.com";
    document.getElementById("smtp_port").value = "587";
    const helpEl = document.getElementById("gmailHelp");
    helpEl.style.display = helpEl.style.display === "none" ? "block" : "none";
    // smtp_user'a focus ver
    document.getElementById("smtp_user").focus();
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
            const levelStr = a.level === "high_high" ? "KRİTİK" : "UYARI";
            const row = document.createElement("tr");
            row.innerHTML = `<td>${timeStr}</td><td>${levelStr}</td><td>${a.dose_rate.toFixed(3)} µSv/h</td><td>${a.action_taken}</td>`;
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
        msgEl.textContent = "Bağlantı hatası"; msgEl.style.color = "var(--red)";
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

// --- API Key ---

let fullApiKey = null;

async function loadApiKey() {
    try {
        const res = await fetch("/api/settings");
        const settings = await res.json();
        const key = settings.api_key || "";
        const display = document.getElementById("apiKeyDisplay");
        if (key) {
            display.value = key.slice(0, 4) + "•".repeat(60);
            fullApiKey = null; // tam key bilinmiyor, sadece maskelenmiş gösterilir
        } else {
            display.value = "";
            display.placeholder = "Henüz üretilmemiş";
        }
    } catch (e) {
        console.error("API key yuklenemedi:", e);
    }
}

document.getElementById("generateApiKeyBtn").addEventListener("click", async () => {
    if (!confirm("Yeni key üretilecek. Eski key geçersiz olacak. Devam?")) return;
    const msgEl = document.getElementById("apiKeyMsg");
    try {
        const res = await fetch("/api/apikey/generate", { method: "POST" });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            msgEl.textContent = err.detail || "Hata oluştu";
            msgEl.style.color = "var(--red)";
            msgEl.classList.add("show");
            setTimeout(() => msgEl.classList.remove("show"), 4000);
            return;
        }
        const data = await res.json();
        fullApiKey = data.api_key;
        document.getElementById("apiKeyDisplay").value = fullApiKey;
        msgEl.textContent = "Key üretildi — kopyalayın!";
        msgEl.style.color = "var(--green)";
        msgEl.classList.add("show");
        setTimeout(() => msgEl.classList.remove("show"), 5000);
    } catch (e) {
        msgEl.textContent = "İstek hatası";
        msgEl.style.color = "var(--red)";
        msgEl.classList.add("show");
        setTimeout(() => msgEl.classList.remove("show"), 4000);
    }
});

document.getElementById("copyApiKeyBtn").addEventListener("click", async () => {
    const display = document.getElementById("apiKeyDisplay");
    const text = fullApiKey || display.value;
    if (!text || text.includes("•")) {
        alert("Kopyalanacak key yok. Önce yeni key üretin.");
        return;
    }
    try {
        await navigator.clipboard.writeText(text);
        const btn = document.getElementById("copyApiKeyBtn");
        const orig = btn.textContent;
        btn.textContent = "Kopyalandı!";
        setTimeout(() => { btn.textContent = orig; }, 2000);
    } catch (e) {
        // Fallback: select input
        display.select();
        document.execCommand("copy");
    }
});

// --- Kullanıcı Yönetimi ---

let currentUsername = null;

async function loadCurrentUser() {
    try {
        const res = await fetch("/api/users/me");
        if (res.ok) {
            const data = await res.json();
            currentUsername = data.username;
        }
    } catch (e) {
        // ignore — currentUsername kalır null
    }
}

async function loadUsers() {
    const container = document.getElementById("userList");
    try {
        const res = await fetch("/api/users");
        if (!res.ok) {
            container.innerHTML = '<span style="color:var(--text-dim)">Kullanıcılar yüklenemedi</span>';
            return;
        }
        const users = await res.json();
        container.innerHTML = "";
        if (users.length === 0) {
            container.innerHTML = '<span style="color:var(--text-dim)">Kullanıcı yok</span>';
            return;
        }
        const table = document.createElement("table");
        table.className = "alarm-table";
        table.innerHTML = "<thead><tr><th>Kullanıcı</th><th>Rol</th><th></th></tr></thead>";
        const tbody = document.createElement("tbody");
        const adminCount = users.filter(u => u.role === "admin").length;
        users.forEach(u => {
            const tr = document.createElement("tr");
            const roleBadge = u.role === "admin"
                ? '<span style="background:var(--accent);color:#fff;padding:0.15rem 0.5rem;border-radius:4px;font-size:0.75rem;">admin</span>'
                : '<span style="background:var(--surface);padding:0.15rem 0.5rem;border-radius:4px;font-size:0.75rem;">viewer</span>';
            const isSelf = u.username === currentUsername;
            const isLastAdmin = u.role === "admin" && adminCount <= 1;
            const disableDelete = isSelf || isLastAdmin;
            tr.innerHTML = `<td>${u.username}</td><td>${roleBadge}</td><td></td>`;
            const delBtn = document.createElement("button");
            delBtn.textContent = "Sil";
            delBtn.style.cssText = "background:none;border:1px solid var(--red);color:var(--red);border-radius:4px;padding:0.15rem 0.5rem;cursor:pointer;font-size:0.75rem;";
            if (disableDelete) {
                delBtn.disabled = true;
                delBtn.style.opacity = "0.3";
                delBtn.style.cursor = "default";
            } else {
                delBtn.addEventListener("click", async () => {
                    if (!confirm(`"${u.username}" silinecek. Emin misiniz?`)) return;
                    try {
                        const r = await fetch(`/api/users/${encodeURIComponent(u.username)}`, { method: "DELETE" });
                        if (r.ok) {
                            loadUsers();
                        } else {
                            const err = await r.json().catch(() => ({}));
                            alert(err.detail || "Silme hatası");
                        }
                    } catch (e) {
                        alert("İstek hatası");
                    }
                });
            }
            tr.lastChild.appendChild(delBtn);
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        container.appendChild(table);
    } catch (e) {
        container.innerHTML = '<span style="color:var(--red)">Kullanıcılar yüklenemedi</span>';
    }
}

document.getElementById("addUserBtn").addEventListener("click", async () => {
    const username = document.getElementById("newUsername").value.trim();
    const password = document.getElementById("newUserPassword").value;
    const role = document.getElementById("newUserRole").value;
    const msgEl = document.getElementById("addUserMsg");
    if (!username || !password) {
        msgEl.textContent = "Kullanıcı adı ve şifre zorunlu";
        msgEl.style.color = "var(--red)";
        msgEl.classList.add("show");
        setTimeout(() => msgEl.classList.remove("show"), 3000);
        return;
    }
    try {
        const res = await fetch("/api/users", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password, role }),
        });
        if (res.ok) {
            document.getElementById("newUsername").value = "";
            document.getElementById("newUserPassword").value = "";
            msgEl.textContent = "Kullanıcı eklendi";
            msgEl.style.color = "var(--green)";
            msgEl.classList.add("show");
            setTimeout(() => msgEl.classList.remove("show"), 3000);
            loadUsers();
        } else {
            const err = await res.json().catch(() => ({}));
            msgEl.textContent = err.detail || "Ekleme hatası";
            msgEl.style.color = "var(--red)";
            msgEl.classList.add("show");
            setTimeout(() => msgEl.classList.remove("show"), 4000);
        }
    } catch (e) {
        msgEl.textContent = "İstek hatası";
        msgEl.style.color = "var(--red)";
        msgEl.classList.add("show");
        setTimeout(() => msgEl.classList.remove("show"), 3000);
    }
});

document.getElementById("changePasswordBtn").addEventListener("click", async () => {
    const currentPw = document.getElementById("currentPassword").value;
    const newPw = document.getElementById("newPassword").value;
    const confirmPw = document.getElementById("confirmPassword").value;
    const msgEl = document.getElementById("changePasswordMsg");
    if (!currentPw || !newPw) {
        msgEl.textContent = "Tüm alanları doldurun";
        msgEl.style.color = "var(--red)";
        msgEl.classList.add("show");
        setTimeout(() => msgEl.classList.remove("show"), 3000);
        return;
    }
    if (newPw !== confirmPw) {
        msgEl.textContent = "Yeni şifreler eşleşmiyor";
        msgEl.style.color = "var(--red)";
        msgEl.classList.add("show");
        setTimeout(() => msgEl.classList.remove("show"), 3000);
        return;
    }
    if (!currentUsername) {
        msgEl.textContent = "Kullanıcı bilgisi alınamadı";
        msgEl.style.color = "var(--red)";
        msgEl.classList.add("show");
        setTimeout(() => msgEl.classList.remove("show"), 3000);
        return;
    }
    try {
        const res = await fetch(`/api/users/${encodeURIComponent(currentUsername)}/password`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ current_password: currentPw, new_password: newPw }),
        });
        if (res.ok) {
            document.getElementById("currentPassword").value = "";
            document.getElementById("newPassword").value = "";
            document.getElementById("confirmPassword").value = "";
            msgEl.textContent = "Şifre güncellendi";
            msgEl.style.color = "var(--green)";
            msgEl.classList.add("show");
            setTimeout(() => msgEl.classList.remove("show"), 3000);
        } else {
            const err = await res.json().catch(() => ({}));
            msgEl.textContent = err.detail || "Şifre güncellenemedi";
            msgEl.style.color = "var(--red)";
            msgEl.classList.add("show");
            setTimeout(() => msgEl.classList.remove("show"), 4000);
        }
    } catch (e) {
        msgEl.textContent = "İstek hatası";
        msgEl.style.color = "var(--red)";
        msgEl.classList.add("show");
        setTimeout(() => msgEl.classList.remove("show"), 3000);
    }
});

// --- SSL Yönetimi ---

async function loadSslStatus() {
    try {
        const res = await fetch("/api/ssl/status");
        if (!res.ok) return;
        const s = await res.json();

        const caDot = document.getElementById("sslCaDot");
        const caText = document.getElementById("sslCaText");
        caDot.className = "conn-dot " + (s.ca_trusted ? "connected" : "");
        caText.textContent = s.ca_trusted ? "Güvenilir" : "Güvenilmiyor";

        const certDot = document.getElementById("sslCertDot");
        const certText = document.getElementById("sslCertText");
        if (s.has_cert) {
            certDot.className = "conn-dot connected";
            let txt = "Aktif";
            if (s.expiry) txt += " (son geçerlilik: " + s.expiry + ")";
            certText.textContent = txt;
        } else {
            certDot.className = "conn-dot";
            certText.textContent = "Yok";
        }

        const httpsDot = document.getElementById("sslHttpsDot");
        const httpsText = document.getElementById("sslHttpsText");
        httpsDot.className = "conn-dot " + (s.ssl_enabled ? "connected" : "");
        httpsText.textContent = s.ssl_enabled ? "Aktif" : "Pasif";
    } catch (e) {
        console.error("SSL durum yüklenemedi:", e);
    }
}

document.getElementById("sslTrustCaBtn").addEventListener("click", async () => {
    const msgEl = document.getElementById("sslCaMsg");
    const fileInput = document.getElementById("caCertFile");
    if (!fileInput.files.length) {
        msgEl.textContent = "Dosya seçin";
        msgEl.style.color = "var(--red)";
        return;
    }
    msgEl.textContent = "CA sertifikası yükleniyor...";
    msgEl.style.color = "var(--text-dim)";
    try {
        const formData = new FormData();
        formData.append("file", fileInput.files[0]);
        const res = await fetch("/api/ssl/trust-ca", { method: "POST", body: formData });
        const data = await res.json();
        msgEl.textContent = data.message;
        msgEl.style.color = data.ok ? "var(--green)" : "var(--red)";
        if (data.ok) { fileInput.value = ""; loadSslStatus(); }
    } catch (e) {
        msgEl.textContent = "İstek hatası";
        msgEl.style.color = "var(--red)";
    }
});

document.getElementById("sslRequestBtn").addEventListener("click", async () => {
    const hostname = document.getElementById("sslHostname").value.trim();
    const msgEl = document.getElementById("sslRequestMsg");
    if (!hostname) {
        msgEl.textContent = "Hostname zorunlu";
        msgEl.style.color = "var(--red)";
        return;
    }
    if (!confirm("Sertifika talep edilecek ve servis yeniden başlatılacak. Devam?")) return;
    msgEl.textContent = "Sertifika talep ediliyor...";
    msgEl.style.color = "var(--text-dim)";
    try {
        const res = await fetch("/api/ssl/request", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ hostname }),
        });
        const data = await res.json();
        msgEl.textContent = data.message;
        msgEl.style.color = data.ok ? "var(--green)" : "var(--red)";
        if (data.ok) {
            setTimeout(() => {
                window.location.protocol = "https:";
                window.location.reload();
            }, 3000);
        }
    } catch (e) {
        msgEl.textContent = "İstek hatası";
        msgEl.style.color = "var(--red)";
    }
});

// --- Init ---

loadSettings();
loadAlarmHistory();
loadWifiStatus();
loadShifts();
loadApiKey();
if (USER_ROLE === "admin") loadSslStatus();
loadCurrentUser().then(() => {
    if (USER_ROLE === "admin") loadUsers();
});

// --- msgService ---

async function msgServiceAction(endpoint, body, resultEl) {
    resultEl.textContent = "İşleniyor...";
    resultEl.style.color = "var(--text-dim)";
    try {
        const res = await fetch(endpoint, {
            method: endpoint.includes("health") ? "GET" : "POST",
            headers: { "Content-Type": "application/json" },
            body: endpoint.includes("health") ? undefined : JSON.stringify(body),
        });
        const data = await res.json();
        if (data.ok) {
            let msg = "Başarılı.";
            if (data.version) msg = `Bağlantı OK — v${data.version} | smtp:${data.smtp || "?"} | wa:${data.whatsapp || "?"}`;
            if (data.messageId) msg = `Gönderildi (ID: ${data.messageId})`;
            if (data.sent !== undefined) msg = `Gönderildi: ${data.sent}/${data.total}`;
            resultEl.textContent = msg;
            resultEl.style.color = "var(--green)";
        } else {
            const errMsg = data.message || data.detail || `HTTP ${res.status}`;
            resultEl.textContent = `Hata: ${errMsg}`;
            resultEl.style.color = "var(--red)";
        }
    } catch (e) {
        resultEl.textContent = `İstek hatası: ${e.message}`;
        resultEl.style.color = "var(--red)";
    }
}

const _msgResult = () => document.getElementById("msgServiceResult");

document.getElementById("msgHealthBtn").addEventListener("click", () =>
    msgServiceAction("/api/msgservice/health", null, _msgResult()));

document.getElementById("msgTestMailHighBtn").addEventListener("click", () =>
    msgServiceAction("/api/msgservice/test-mail", { level: "high" }, _msgResult()));

document.getElementById("msgTestMailHHBtn").addEventListener("click", () =>
    msgServiceAction("/api/msgservice/test-mail", { level: "high_high" }, _msgResult()));

document.getElementById("msgTestWaHighBtn").addEventListener("click", () =>
    msgServiceAction("/api/msgservice/test-wa", { level: "high" }, _msgResult()));

document.getElementById("msgTestWaHHBtn").addEventListener("click", () =>
    msgServiceAction("/api/msgservice/test-wa", { level: "high_high" }, _msgResult()));
