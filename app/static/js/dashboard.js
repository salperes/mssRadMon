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
const shiftNameEl = document.getElementById("shiftName");
const shiftDoseEl = document.getElementById("shiftDose");
const shiftHistoryBody = document.getElementById("shiftHistoryBody");
const monthlyDoseEl = document.getElementById("monthlyDose");
const quarterlyDoseEl = document.getElementById("quarterlyDose");
const halfYearlyDoseEl = document.getElementById("halfYearlyDose");
const yearlyDoseEl = document.getElementById("yearlyDose");

let thresholdHigh = 0.5;
let thresholdHighHigh = 1.0;
let currentRange = "1h";

const ctx = document.getElementById("doseChart").getContext("2d");
const chart = new Chart(ctx, {
    type: "line",
    data: {
        labels: [],
        datasets: [{
            label: "Doz Hizi (µSv/h)",
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
                ticks: { color: "#64748b", maxTicksLimit: 12, font: { size: 11 } },
                grid: { color: "rgba(0,0,0,0.06)" },
            },
            y: {
                ticks: { color: "#64748b", font: { size: 11 } },
                grid: { color: "rgba(0,0,0,0.06)" },
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
                        borderColor: "#d97706",
                        borderWidth: 1.5,
                        borderDash: [6, 4],
                        label: {
                            display: true,
                            content: "High",
                            position: "start",
                            backgroundColor: "rgba(217,119,6,0.1)",
                            color: "#d97706",
                            font: { size: 10 },
                            padding: 3,
                        },
                    },
                    highHighLine: {
                        type: "line",
                        yMin: thresholdHighHigh,
                        yMax: thresholdHighHigh,
                        borderColor: "#dc2626",
                        borderWidth: 1.5,
                        borderDash: [6, 4],
                        label: {
                            display: true,
                            content: "High-High",
                            position: "start",
                            backgroundColor: "rgba(220,38,38,0.1)",
                            color: "#dc2626",
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
    connText.textContent = connected ? "Bağlı" : "Bağlantı yok";
}

function updateShift(active, name, dose) {
    if (active && name) {
        shiftNameEl.textContent = name;
        shiftDoseEl.textContent = dose.toFixed(3);
    } else {
        shiftNameEl.textContent = "Vardiya dışı";
        shiftDoseEl.textContent = "—";
    }
}

function updatePendingAlarm(pending, level, elapsed, duration) {
    if (pending) {
        const levelText = level === "high_high" ? "KRİTİK eşik aşıldı" : "HIGH eşiği aşıldı";
        alarmBanner.className = "alarm-banner active " + (level === "high_high" ? "high_high" : "high");
        alarmLevel.textContent = "ÖN UYARI";
        alarmMsg.textContent = `${levelText} — ${elapsed}/${duration} sn`;
    }
}

async function loadPeriodDoses() {
    try {
        const res = await fetch("/api/period-doses");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
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

function formatTime(isoStr) {
    const d = new Date(isoStr);
    if (currentRange === "7d" || currentRange === "30d") {
        return d.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit" })
            + " " + d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function setChartData(readings) {
    chartInteraction.resetView();
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
        if (current.alarm_pending) {
            updatePendingAlarm(true, current.alarm_pending_level, current.alarm_pending_elapsed, current.alarm_pending_duration);
        }

        await loadPeriodDoses();

        const shiftRes = await fetch("/api/shift/current");
        const shift = await shiftRes.json();
        updateShift(shift.active, shift.shift_name, shift.shift_dose);

        await loadShiftHistory();

        const alarmsRes = await fetch("/api/alarms?last=24h");
        const alarms = await alarmsRes.json();
        if (alarms.length > 0) {
            const last = alarms[0];
            alarmBanner.className = "alarm-banner active " + last.level;
            alarmLevel.textContent = last.level === "high_high" ? "KRİTİK ALARM" : "UYARI";
            alarmMsg.textContent = `${last.dose_rate.toFixed(3)} µSv/h - ${formatTime(last.timestamp)}`;
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
            loadPeriodDoses();
            updateShift(msg.shift_active, msg.shift_name, msg.shift_dose);
            if (msg.alarm_pending) {
                updatePendingAlarm(true, msg.alarm_pending_level, msg.alarm_pending_elapsed, msg.alarm_pending_duration);
            } else {
                alarmBanner.className = "alarm-banner";
            }
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

setInterval(loadPeriodDoses, 60000);

loadInitial();
connectWS();

// ---- Grafik etkileşimi: ROI zum (sol), pan (sağ), scroll zum, çift tık reset ----
const chartInteraction = (() => {
    const cv = document.getElementById("doseChart");
    const container = cv.parentElement; // .chart-container (position:relative)

    // Seçim kutusu overlay
    const selBox = document.createElement("div");
    selBox.style.cssText = "position:absolute;border:1px solid rgba(0,188,212,0.7);background:rgba(0,188,212,0.08);pointer-events:none;display:none;box-sizing:border-box;";
    container.appendChild(selBox);

    let drag = null; // { type:"zoom"|"pan", startX, viewStart, viewEnd }

    function labelIndexAt(px) {
        const scale = chart.scales.x;
        if (!scale || !chart.data.labels.length) return 0;
        const idx = Math.round(scale.getValueForPixel(px));
        return Math.max(0, Math.min(idx, chart.data.labels.length - 1));
    }

    function currentViewIndices() {
        const labels = chart.data.labels;
        if (!labels.length) return [0, 0];
        const minL = chart.options.scales.x.min;
        const maxL = chart.options.scales.x.max;
        const s = (minL !== undefined) ? labels.indexOf(minL) : 0;
        const e = (maxL !== undefined) ? labels.indexOf(maxL) : labels.length - 1;
        return [s < 0 ? 0 : s, e < 0 ? labels.length - 1 : e];
    }

    function applyView(s, e) {
        const labels = chart.data.labels;
        if (!labels.length) return;
        s = Math.max(0, s);
        e = Math.min(labels.length - 1, e);
        if (e - s < 2) return;
        chart.options.scales.x.min = labels[s];
        chart.options.scales.x.max = labels[e];
        chart.update("none");
    }

    function resetView() {
        delete chart.options.scales.x.min;
        delete chart.options.scales.x.max;
        chart.update("none");
    }

    // Sol fare tuşu: ROI zum başlat
    cv.addEventListener("mousedown", e => {
        if (e.button === 0) {
            drag = { type: "zoom", startX: e.offsetX };
            cv.style.cursor = "crosshair";
        } else if (e.button === 2) {
            const [vs, ve] = currentViewIndices();
            drag = { type: "pan", startX: e.offsetX, viewStart: vs, viewEnd: ve };
            cv.style.cursor = "grabbing";
        }
    });

    cv.addEventListener("mousemove", e => {
        if (!drag) return;
        const ca = chart.chartArea;
        if (!ca) return;

        if (drag.type === "zoom") {
            const x1 = Math.max(ca.left, Math.min(drag.startX, e.offsetX));
            const x2 = Math.min(ca.right, Math.max(drag.startX, e.offsetX));
            if (x2 - x1 > 4) {
                selBox.style.left   = x1 + "px";
                selBox.style.top    = ca.top + "px";
                selBox.style.width  = (x2 - x1) + "px";
                selBox.style.height = (ca.bottom - ca.top) + "px";
                selBox.style.display = "block";
            }
        } else if (drag.type === "pan") {
            const dx = e.offsetX - drag.startX;
            const { viewStart: vs, viewEnd: ve } = drag;
            const viewLen = ve - vs || 1;
            const chartW = ca.right - ca.left;
            const delta = Math.round(-dx * viewLen / chartW);
            applyView(vs + delta, ve + delta);
        }
    });

    cv.addEventListener("mouseup", e => {
        if (!drag) return;
        if (drag.type === "zoom" && e.button === 0) {
            selBox.style.display = "none";
            const dx = Math.abs(e.offsetX - drag.startX);
            if (dx > 10) {
                applyView(
                    labelIndexAt(Math.min(drag.startX, e.offsetX)),
                    labelIndexAt(Math.max(drag.startX, e.offsetX))
                );
            }
        }
        drag = null;
        cv.style.cursor = "";
    });

    cv.addEventListener("mouseleave", () => {
        if (drag && drag.type === "zoom") selBox.style.display = "none";
        drag = null;
        cv.style.cursor = "";
    });

    // Scroll: zum in/out (imleç konumu merkez)
    cv.addEventListener("wheel", e => {
        e.preventDefault();
        const ca = chart.chartArea;
        if (!ca) return;
        const [vs, ve] = currentViewIndices();
        const viewLen = ve - vs || 1;
        const factor = e.deltaY > 0 ? 1.25 : 0.8; // scroll aşağı = uzaklaş
        const newLen = Math.round(viewLen * factor);
        // İmleç hangi orana denk geliyor?
        const ratio = Math.max(0, Math.min(1, (e.offsetX - ca.left) / (ca.right - ca.left)));
        const pivot = vs + Math.round(ratio * viewLen);
        const newStart = Math.round(pivot - ratio * newLen);
        const newEnd   = newStart + newLen;
        if (newLen >= chart.data.labels.length) {
            resetView();
        } else {
            applyView(newStart, newEnd);
        }
    }, { passive: false });

    // Çift tık: sıfırla
    cv.addEventListener("dblclick", () => resetView());

    // Sağ tık menüsünü engelle
    cv.addEventListener("contextmenu", e => e.preventDefault());

    return { resetView };
})();
