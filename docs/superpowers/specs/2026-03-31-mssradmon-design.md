# mssRadMon — GammaScout Radyasyon Monitörü Tasarım Dokümanı

**Tarih:** 2026-03-31  
**Platform:** Raspberry Pi 5 (aarch64), Python 3.13  
**Cihaz:** GammaScout Online (Seri No: GSNJR400), /dev/ttyUSB0, FTDI chip

---

## 1. Amaç

Raspberry Pi'ye USB üzerinden bağlı GammaScout Online radyasyon ölçerden anlık doz hızı ve kümülatif doz verilerini okuyarak:

- Verileri yerel veritabanında saklamak
- Web arayüzü üzerinden anlık ve geçmiş verileri görselleştirmek
- Eşik değerlerine göre alarm (buzzer, ışık, acil kapatma, e-posta) üretmek
- Verileri uzak bir log sunucusuna iletmek

## 2. Mimari

Tek Python proses, asyncio tabanlı. Tüm bileşenler aynı event loop içinde çalışır.

```
┌─────────────┐    serial     ┌──────────────────────────────────┐
│ GammaScout  │──────────────▶│  mssRadMon (tek Python proses)   │
│ Online      │  /dev/ttyUSB0 │                                  │
└─────────────┘               │  ┌────────────┐  ┌───────────┐  │
                              │  │ Serial      │  │ FastAPI   │  │
┌─────────────┐               │  │ Reader      │─▶│ (HTTP +   │  │
│ GPIO        │◀──────────────│  │ (asyncio)   │  │ WebSocket)│  │
│ Buzzer      │               │  └─────┬──────┘  └─────┬─────┘  │
│ Light       │               │        │                │        │
│ Emergency   │               │        ▼                ▼        │
└─────────────┘               │  ┌─────────────────────────┐     │
                              │  │   SQLite (readings.db)  │     │
                              │  └─────────────────────────┘     │
                              │                                  │
                              │  ┌────────────┐  ┌───────────┐  │
                              │  │ Alarm      │  │ Remote    │  │
                              │  │ Manager    │  │ Log Fwd   │  │
                              │  └────────────┘  └───────────┘  │
                              └──────────────────────────────────┘
                                         ▲
                                         │ HTTP/WS (LAN)
                                    ┌────┴────┐
                                    │ Browser │
                                    └─────────┘
```

**Teknoloji seçimleri:**

- **Backend:** Python 3.13 + FastAPI (REST + WebSocket)
- **DB:** SQLite (tek dosya, sıfır bakım)
- **Frontend:** Vanilla HTML/CSS/JS + Chart.js
- **Serial:** pyserial + asyncio
- **GPIO:** gpiozero veya RPi.GPIO
- **Deploy:** systemd unit
- **Erişim:** Sadece yerel ağ, kimlik doğrulama yok

## 3. Serial Haberleşme

GammaScout Online cihazı PC Mode destekler. Protokol parametreleri implementasyon sırasında cihaz üzerinde test edilip dokümente edilecektir (`docs/serial_protocol.md`).

**Bilinen/beklenen parametreler (doğrulanacak):**

- Port: `/dev/ttyUSB0`
- Baud rate: 9600 (doğrulanacak)
- Data bits: 7, Parity: even, Stop bits: 1 (doğrulanacak)
- PC mode giriş: `P` komutu
- PC mode çıkış: `X` komutu

**Serial Reader modülü:**

- asyncio task olarak çalışır
- `sampling_interval` (default 10s) aralıklarla veri okur
- Her okumada parse edilen veri:
  - `timestamp` (UTC)
  - `dose_rate` (µSv/h) — anlık doz hızı
  - `cumulative_dose` (µSv) — kümülatif doz
- Okunan veri: SQLite'a yazılır, WebSocket'e push edilir, Alarm Manager'a iletilir

**Hata yönetimi:**

- USB bağlantı kopması: otomatik reconnect (5s aralıklarla)
- Reconnect sırasında web arayüzünde "cihaz bağlantısı yok" uyarısı

## 4. Veritabanı

**SQLite — `data/readings.db`**

```sql
CREATE TABLE readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,          -- ISO 8601 UTC
    dose_rate REAL NOT NULL,          -- µSv/h
    cumulative_dose REAL NOT NULL,    -- µSv
    remote_synced INTEGER DEFAULT 0   -- 0: gönderilmedi, 1: gönderildi
);
CREATE INDEX idx_readings_ts ON readings(timestamp);
CREATE INDEX idx_readings_sync ON readings(remote_synced) WHERE remote_synced = 0;

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE alarm_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,               -- 'high' veya 'high_high'
    dose_rate REAL NOT NULL,
    action_taken TEXT NOT NULL,         -- 'buzzer,light', 'buzzer,light,emergency' vb.
    remote_synced INTEGER DEFAULT 0
);
CREATE INDEX idx_alarm_ts ON alarm_log(timestamp);
CREATE INDEX idx_alarm_sync ON alarm_log(remote_synced) WHERE remote_synced = 0;
```

**Settings varsayılan değerleri:**

| key | default | açıklama |
|-----|---------|----------|
| `sampling_interval` | `10` | Örnekleme aralığı (saniye) |
| `threshold_high` | `0.5` | High alarm eşiği (µSv/h) |
| `threshold_high_high` | `1.0` | High-High alarm eşiği (µSv/h) |
| `alarm_buzzer_enabled` | `true` | Buzzer aktif mi |
| `alarm_email_enabled` | `false` | E-posta bildirimi aktif mi |
| `alarm_email_to` | `""` | Alıcı e-posta adresi |
| `smtp_host` | `""` | SMTP sunucu |
| `smtp_port` | `587` | SMTP port |
| `smtp_user` | `""` | SMTP kullanıcı |
| `smtp_pass` | `""` | SMTP şifre |
| `remote_log_enabled` | `false` | Remote log aktif mi |
| `remote_log_url` | `""` | Remote log endpoint URL |
| `remote_log_api_key` | `""` | Remote log API anahtarı |
| `gpio_buzzer_pin` | `17` | Buzzer GPIO pin numarası |
| `gpio_light_pin` | `27` | Işık GPIO pin numarası |
| `gpio_emergency_pin` | `22` | Acil kapatma GPIO pin numarası |
| `alarm_high_actions` | `buzzer,light` | High alarmda tetiklenecek aksiyonlar |
| `alarm_high_high_actions` | `buzzer,light,emergency` | High-High alarmda tetiklenecek aksiyonlar |

**Veri hacmi:** ~8640 kayıt/gün, ~3.15M/yıl, ~300-350 MB/yıl. Retention policy gerekmez.

## 5. Web Arayüzü

Dil: Türkçe. Responsive tasarım (mobil uyumlu).

### Dashboard (`/`)

- **Anlık doz hızı:** Büyük rakamsal gösterge (µSv/h), renk kodlu:
  - Yeşil: normal
  - Sarı: >= High eşiği
  - Kırmızı: >= High-High eşiği
- **1 saatlik doz hızı grafiği:** Kayan pencere, Chart.js line chart, WebSocket ile canlı güncelleme
- **Günlük kümülatif doz:** Sayısal gösterge (µSv), bugün 00:00 UTC'den itibaren toplam doz (readings tablosundan hesaplanır, ayrı bir alan değil)
- **Cihaz durumu:** Bağlı/bağlı değil göstergesi
- **Son alarm:** Varsa son alarm bilgisi

### Admin (`/admin`)

- **Eşik değerleri:** High ve High-High threshold (µSv/h)
- **Alarm ayarları:** Buzzer, e-posta (alıcı + SMTP), GPIO pin atamaları, seviye-aksiyon eşleştirmeleri
- **Örnekleme:** Sampling interval (saniye)
- **Remote log:** Açık/kapalı, URL, API key
- **Alarm geçmişi:** Son alarmların listesi (tarih, seviye, aksiyon)

### Teknik

- Vanilla HTML/CSS/JS, harici framework yok
- Chart.js (lokal kopya `static/lib/` altında)
- FastAPI Jinja2 template'leri ile sunulur

## 6. REST API ve WebSocket

```
GET  /api/current              # Son okuma (anlık doz hızı + kümülatif)
GET  /api/readings?last=1h     # Son X süredeki okumalar (1h, 24h, 7d)
GET  /api/daily-dose           # Bugünkü kümülatif doz
GET  /api/status               # Cihaz bağlantı durumu + uptime
GET  /api/alarms?last=24h      # Alarm geçmişi

WS   /ws/live                  # Canlı veri akışı (WebSocket)

GET  /api/settings             # Tüm ayarları getir
PUT  /api/settings             # Ayarları güncelle (JSON body)

GET  /                         # Dashboard sayfası
GET  /admin                    # Admin sayfası
```

Poll ve push birlikte desteklenir.

## 7. Alarm Sistemi

**İki seviyeli alarm:**

| Seviye | Varsayılan Eşik | Varsayılan Aksiyonlar |
|--------|-----------------|----------------------|
| High | 0.5 µSv/h | buzzer + light |
| High-High | 1.0 µSv/h | buzzer + light + emergency |

**GPIO çıkışları:**

| Çıkış | Varsayılan Pin | Açıklama |
|-------|---------------|----------|
| buzzer | GPIO 17 | Sesli alarm |
| light | GPIO 27 | Işıklı uyarı |
| emergency | GPIO 22 | Acil kapatma rölesi |

**Akış:**

1. Her yeni okumada `dose_rate` threshold'lara karşı kontrol edilir
2. Eşik aşılırsa: ilgili GPIO çıkışları tetiklenir, e-posta gönderilir (aktifse), `alarm_log`'a yazılır
3. Aynı seviyedeki alarm temizlenene kadar tekrar tetiklenmez (doz hızı eşiğin altına düşünce reset)
4. Buzzer davranışı:
   - High: 1s bip, 5s arayla tekrar
   - High-High: sürekli bip (doz düşene veya acknowledge edilene kadar)

**E-posta:** Doğrudan SMTP. İleride harici msgService API entegrasyonu eklenecek.

## 8. Remote Log Forwarding

HTTP POST ile uzak sunucuya veri iletimi.

**Payload:**

```json
// Ölçüm
POST {remote_log_url}/reading
Headers: X-API-Key: {api_key}
{"device_id": "GSNJR400", "timestamp": "...", "dose_rate": 0.12, "cumulative_dose": 45.6}

// Alarm
POST {remote_log_url}/alarm
Headers: X-API-Key: {api_key}
{"device_id": "GSNJR400", "timestamp": "...", "level": "high", "dose_rate": 0.55, "action_taken": "buzzer,light"}
```

**Persistent queue mekanizması:**

- `readings` ve `alarm_log` tablolarındaki `remote_synced` kolonu ile takip
- Push başarılıysa `remote_synced = 1` işaretlenir
- Başarısızsa satır `remote_synced = 0` kalır
- Bağlantı tekrar sağlandığında `remote_synced = 0` kayıtlar kronolojik sırayla batch halinde (100'lük gruplar) gönderilir
- Retry: 3 deneme, exponential backoff (5s, 15s, 45s)
- Remote log hatası ana veri toplama döngüsünü bloklamaz (async)

## 9. Proje Yapısı

```
mssRadMon/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, startup/shutdown
│   ├── config.py            # Settings yönetimi (DB'den okuma/yazma)
│   ├── serial_reader.py     # GammaScout serial haberleşme
│   ├── db.py                # SQLite bağlantı ve migration
│   ├── alarm.py             # Alarm manager + GPIO kontrol
│   ├── remote_log.py        # Remote log forwarding + sync
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── api.py           # REST endpointleri (poll desteği)
│   │   ├── ws.py            # WebSocket endpoint
│   │   └── admin.py         # Admin API endpointleri
│   ├── templates/
│   │   ├── dashboard.html   # Ana sayfa
│   │   └── admin.html       # Admin sayfası
│   └── static/
│       ├── css/
│       ├── js/
│       └── lib/             # Chart.js lokal kopyası
├── data/                    # readings.db burada oluşur (gitignore)
├── docs/
│   └── serial_protocol.md   # GammaScout protokol dökümantasyonu
├── requirements.txt
├── systemd/
│   └── mssradmon.service    # systemd unit dosyası
├── .gitignore
└── README.md
```

## 10. Deploy

- systemd service olarak çalışır
- Otomatik restart (on-failure)
- `data/` dizini persistent
- Uygulama `0.0.0.0:8080` üzerinde dinler (port ayarlanabilir)
