# mssRadMon

GammaScout radyasyon dedektöründen seri port üzerinden anlık doz hızı (µSv/h) ve kümülatif doz okuyan, web arayüzü ile görselleştiren Raspberry Pi tabanlı izleme sistemi.

## Teknoloji

- **Backend:** Python 3.11+, FastAPI, Uvicorn
- **Veritabanı:** SQLite (aiosqlite), `data/readings.db`
- **Frontend:** Vanilla JS, Chart.js, Bootstrap 5 (CDN yok, static/lib altında)
- **Cihaz iletişimi:** pyserial ile `/dev/ttyUSB0` (FTDI USB-Serial)
- **Donanım:** Raspberry Pi, GPIO üzerinden buzzer/ışık/acil durum çıkışları (gpiozero)

## Proje Yapısı

```
app/
  main.py          # FastAPI uygulama giriş noktası, lifespan yönetimi
  config.py        # SQLite settings tablosu üzerinden ayar yönetimi
  db.py            # aiosqlite veritabanı katmanı
  serial_reader.py # GammaScout seri port okuyucu
  alarm.py         # Alarm yönetimi (eşik, süre, buzzer, ışık)
  shift.py         # Vardiya yönetimi ve doz takibi
  remote_log.py    # Uzak sunucuya log iletimi
  wifi.py          # WiFi otomatik bağlantı ve alarm durumunda AP geçişi
  routers/
    api.py         # REST API endpointleri
    ws.py          # WebSocket (anlık okuma push)
    admin.py       # Admin panel API'leri
  templates/
    dashboard.html # Ana izleme ekranı
    admin.html     # Ayar ve yönetim paneli
  static/
    css/style.css
    js/            # dashboard.js, admin.js
    lib/           # Chart.js, Bootstrap (yerel kopyalar)
systemd/
  mssradmon.service  # Systemd servis tanımı
```

## Çalıştırma

```bash
# Geliştirme
source .venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload

# Üretim (systemd)
sudo systemctl start mssradmon
```

Web arayüzü: `http://<ip>:8090`

## Temel Kavramlar

- **Okuma döngüsü:** `serial_reader.py` belirli aralıklarla (varsayılan 10s) GammaScout'tan doz hızı okur, callback ile `main.py`'deki `on_reading` tetiklenir.
- **Alarm sistemi:** İki seviye (high / high-high), her biri için ayrı süre eşiği var. Eşik süre boyunca aşılırsa alarm tetiklenir. GPIO buzzer/ışık/acil durum çıkışları ve opsiyonel e-posta bildirimi.
- **Vardiya yönetimi:** Vardiyalar JSON olarak config'de saklanır. Aktif vardiya süresince kümülatif doz farkı takip edilir.
- **Remote log:** Okumaları uzak HTTP endpointine iletir, bağlantı kesildiğinde kuyruklar ve sonra senkronize eder.
- **Ayarlar:** Tüm konfigürasyon SQLite `settings` tablosunda key-value olarak tutulur, admin panelinden değiştirilebilir.

## Testler

```bash
source .venv/bin/activate
pytest
```

## Ortam Değişkenleri

- `MSSRADMON_DB_PATH` — Veritabanı dosya yolu (varsayılan: `data/readings.db`)
