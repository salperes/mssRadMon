"use strict";

const POLL_INTERVAL = 10000;
const WS_RECONNECT_DELAY = 3000;

const doseRateEl = document.getElementById("doseRate");
const dailyDoseEl = document.getElementById("dailyDose");
const connDot = document.getElementById("connDot");
const connText = document.getElementById("connText");
const alarmBanner = document.getElementById("alarmBanner");
const alarmLevel = document.getElementById("alarmLevel");
const alarmMsg = document.getElementById("alarmMsg");

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

    const maxPoints = 360;
    if (chart.data.labels.length > maxPoints) {
        chart.data.labels.shift();
        chart.data.datasets[0].data.shift();
    }
    chart.update("none");
}

async function loadInitial() {
    try {
        const settingsRes = await fetch("/api/settings");
        const settings = await settingsRes.json();
        thresholdHigh = parseFloat(settings.threshold_high || "0.5");
        thresholdHighHigh = parseFloat(settings.threshold_high_high || "1.0");

        const readingsRes = await fetch("/api/readings?last=1h");
        const readings = await readingsRes.json();
        readings.forEach(r => addChartPoint(r.timestamp, r.dose_rate));

        const currentRes = await fetch("/api/current");
        const current = await currentRes.json();
        if (current.dose_rate !== null) {
            updateDoseRate(current.dose_rate);
        }
        updateConnection(current.connected);

        const dailyRes = await fetch("/api/daily-dose");
        const daily = await dailyRes.json();
        dailyDoseEl.textContent = daily.daily_dose.toFixed(3);

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

setInterval(async () => {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();
        updateConnection(data.connected);
    } catch (e) { /* ignore */ }
}, 5000);

loadInitial();
connectWS();
