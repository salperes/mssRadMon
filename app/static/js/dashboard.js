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
const chartRangeEl = document.getElementById("chartRange");

let thresholdHigh = 0.5;
let thresholdHighHigh = 1.0;
let currentRange = "1h";

const ctx = document.getElementById("doseChart").getContext("2d");
const chart = new Chart(ctx, {
    type: "line",
    data: {
        labels: [],
        datasets: [{
            label: "Doz Hizi (uSv/h)",
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
            annotation: {
                annotations: {
                    highLine: {
                        type: "line",
                        yMin: thresholdHigh,
                        yMax: thresholdHigh,
                        borderColor: "#ffd600",
                        borderWidth: 1.5,
                        borderDash: [6, 4],
                        label: {
                            display: true,
                            content: "High",
                            position: "start",
                            backgroundColor: "rgba(255,214,0,0.2)",
                            color: "#ffd600",
                            font: { size: 10 },
                            padding: 3,
                        },
                    },
                    highHighLine: {
                        type: "line",
                        yMin: thresholdHighHigh,
                        yMax: thresholdHighHigh,
                        borderColor: "#ff1744",
                        borderWidth: 1.5,
                        borderDash: [6, 4],
                        label: {
                            display: true,
                            content: "High-High",
                            position: "start",
                            backgroundColor: "rgba(255,23,68,0.2)",
                            color: "#ff1744",
                            font: { size: 10 },
                            padding: 3,
                        },
                    },
                },
            },
        },
    },
});

function updateThresholdLines() {
    const ann = chart.options.plugins.annotation.annotations;
    ann.highLine.yMin = thresholdHigh;
    ann.highLine.yMax = thresholdHigh;
    ann.highHighLine.yMin = thresholdHighHigh;
    ann.highHighLine.yMax = thresholdHighHigh;
    chart.update("none");
}

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
    connText.textContent = connected ? "Bagli" : "Baglanti yok";
}

function formatTime(isoStr) {
    const d = new Date(isoStr);
    if (currentRange === "7d" || currentRange === "30d") {
        return d.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit" })
            + " " + d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function setChartData(readings) {
    chart.data.labels = readings.map(r => formatTime(r.timestamp));
    chart.data.datasets[0].data = readings.map(r => r.dose_rate);
    chart.update();
}

function addChartPoint(timestamp, value) {
    chart.data.labels.push(formatTime(timestamp));
    chart.data.datasets[0].data.push(value);

    const maxPoints = 3600;
    if (chart.data.labels.length > maxPoints) {
        chart.data.labels.shift();
        chart.data.datasets[0].data.shift();
    }
    chart.update("none");
}

async function loadReadings(range) {
    try {
        const res = await fetch(`/api/readings?last=${range}`);
        const readings = await res.json();
        setChartData(readings);
    } catch (e) {
        console.error("Okumalar yuklenemedi:", e);
    }
}

chartRangeEl.addEventListener("change", () => {
    currentRange = chartRangeEl.value;
    loadReadings(currentRange);
});

async function loadInitial() {
    try {
        const settingsRes = await fetch("/api/settings");
        const settings = await settingsRes.json();
        thresholdHigh = parseFloat(settings.threshold_high || "0.5");
        thresholdHighHigh = parseFloat(settings.threshold_high_high || "1.0");
        updateThresholdLines();

        await loadReadings(currentRange);

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
            alarmLevel.textContent = last.level === "high_high" ? "KRITIK ALARM" : "UYARI";
            alarmMsg.textContent = `${last.dose_rate.toFixed(3)} uSv/h - ${formatTime(last.timestamp)}`;
        }
    } catch (e) {
        console.error("Baslangic verileri yuklenemedi:", e);
    }
}

let ws = null;

function connectWS() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws/live`);

    ws.onopen = () => console.log("WebSocket baglandi");

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
        console.log("WebSocket kapandi, yeniden baglaniliyor...");
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
