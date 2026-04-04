# mssRadMon — Manager Entegrasyon Rehberi

Bu doküman, birden fazla mssRadMon cihazını merkezi olarak izleyen bir **manager uygulamasının** hangi veriyi, nasıl çekeceğini anlatır.

Her mssRadMon cihazı bağımsız bir HTTP sunucusudur. Manager, N adet cihaza aynı API'yi kullanarak bağlanır.

---

## Temel Bilgiler

| Parametre | Değer |
|---|---|
| Varsayılan port | `8090` |
| Base URL | `http://<cihaz-ip>:8090` veya `https://<cihaz-ip>:8090` (SSL aktifse) |
| Protokol | HTTP/1.1 + WebSocket |
| İçerik tipi | `application/json` |
| API kimlik doğrulama | Tüm `/api/*` endpoint'leri API key gerektirir (`X-API-Key` header) |
| Admin kimlik doğrulama | `/admin/*` rotaları cookie-based session gerektirir |

---

## API Key ile Bağlantı

Tüm `/api/*` endpoint'leri `X-API-Key` header'ı ile doğrulama gerektirir. WebSocket (`/ws/live`) muaftır.

### API Key Alma

1. Cihazın admin paneline gidin: `http://<cihaz-ip>:8090/admin`
2. Sidebar'da **"API Erişimi"** bölümüne tıklayın
3. **"Yeni Key Üret"** butonuna tıklayın
4. Gösterilen 64 karakterlik key'i kopyalayın — bu key yalnızca bir kez tam olarak gösterilir

### Kullanım

Her API isteğine `X-API-Key` header'ı ekleyin:

```bash
curl -H "X-API-Key: <api-key>" http://<cihaz-ip>:8090/api/current
```

```python
import httpx

client = httpx.Client(
    base_url="http://192.168.1.100:8090",
    headers={"X-API-Key": "a3f9...64_karakter_hex..."},
)
data = client.get("/api/current").json()
```

### Hata Yanıtları

| HTTP Kodu | Durum | Açıklama |
|---|---|---|
| `401 Unauthorized` | `{"detail": "Geçersiz API key"}` | Key yanlış veya eksik |
| `503 Service Unavailable` | `{"detail": "API key henüz üretilmemiş"}` | Admin panelden key üretilmemiş |

> **Not:** API key değiştirildiğinde eski key geçersiz olur — manager'daki key'i güncellemeyi unutmayın.

---

## Veri Çekme Yöntemleri

### 1. Periyodik Polling (REST)

Düşük frekanslı izleme veya geçmiş sorguları için uygundur. Cihazı her `n` saniyede bir sorgulayın.

### 2. Gerçek Zamanlı Push (WebSocket)

Her yeni ölçüm geldiğinde (~10 saniyede bir) cihaz, bağlı tüm WebSocket istemcilerine otomatik mesaj gönderir. Canlı dashboard için önerilen yöntemdir.

---

## REST API Endpoint'leri

### Sağlık ve Durum

#### `GET /api/health`
Cihazın ayakta olup olmadığını ve versiyonunu döndürür. Manager'ın periyodik "heartbeat" kontrolü için kullanın.

```json
{
  "status": "ok",
  "version": "1.2.0"
}
```

#### `GET /api/status`
Seri port bağlantı durumunu döndürür.

```json
{
  "connected": true,
  "port": "/dev/ttyUSB0",
  "version": "1.2.0"
}
```

- `connected: false` → Dedektör fiziksel olarak bağlı değil veya seri port okuyamıyor.

---

### Anlık Ölçüm

#### `GET /api/current`
En son ölçüm değerini döndürür. Polling tabanlı izlemede temel endpoint.

```json
{
  "timestamp": "2026-04-03T14:32:10.123456+00:00",
  "dose_rate": 0.142,
  "cumulative_dose": 4521.338,
  "connected": true,
  "alarm_pending": false,
  "alarm_pending_level": null,
  "alarm_pending_elapsed": 0,
  "alarm_pending_duration": 0
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `timestamp` | ISO 8601 UTC | Ölçüm zamanı |
| `dose_rate` | float (µSv/h) | Anlık doz hızı |
| `cumulative_dose` | float (µSv) | Cihaz açıldığından beri toplam kümülatif doz |
| `connected` | bool | Dedektör bağlı mı |
| `alarm_pending` | bool | Eşik aşıldı, süre dolmadı (pre-alarm) |
| `alarm_pending_level` | `"high"` \| `"high_high"` \| null | Hangi eşikte bekliyor |
| `alarm_pending_elapsed` | int (sn) | Eşiğin kaç saniyedir aşıldığı |
| `alarm_pending_duration` | int (sn) | Alarm tetiklenmesi için gereken süre |

---

### Tarihsel Ölçümler

#### `GET /api/readings?last=<period>`
Belirli zaman aralığındaki tüm ölçümleri döndürür. Grafik çizmek için kullanın.

**`last` parametresi:** `1h` | `6h` | `24h` | `7d` | `30d` (varsayılan: `1h`)

```json
[
  {
    "timestamp": "2026-04-03T11:00:00+00:00",
    "dose_rate": 0.138,
    "cumulative_dose": 4518.201
  },
  {
    "timestamp": "2026-04-03T11:00:10+00:00",
    "dose_rate": 0.141,
    "cumulative_dose": 4518.202
  }
]
```

> **Not:** Okumalar ~10 saniyede bir alınır. `7d` sorgusu yüksek hacimli veri döndürebilir (~60.000 satır). Manager'da sayfalama/örnekleme uygulamanız önerilir.

---

### Doz Özetleri

#### `GET /api/daily-dose`
Bugün (UTC+3 gece yarısından itibaren) biriken toplam doz farkı.

```json
{
  "date": "2026-04-03",
  "daily_dose": 3.412
}
```

#### `GET /api/period-doses`
Günlük, aylık, çeyreklik, 6 aylık ve yıllık doz özetleri. Manager'ın özet kartları için ideal.

```json
{
  "daily": 3.412,
  "monthly": 89.23,
  "quarterly": 267.41,
  "half_yearly": 512.88,
  "yearly": 1024.55
}
```

Tüm değerler **µSv** cinsindendir ve UTC+3 takvim dönemlerine göre hesaplanır.

---

### Alarm Geçmişi

#### `GET /api/alarms?last=<period>`
Tetiklenmiş alarm kayıtlarını döndürür.

**`last` parametresi:** `1h` | `6h` | `24h` | `7d` | `30d` (varsayılan: `24h`)

```json
[
  {
    "timestamp": "2026-04-03T09:15:22+00:00",
    "level": "high",
    "dose_rate": 0.623,
    "action_taken": "buzzer,light"
  }
]
```

| Alan | Açıklama |
|---|---|
| `level` | `"high"` veya `"high_high"` |
| `dose_rate` | Alarm anındaki doz hızı (µSv/h) |
| `action_taken` | Tetiklenen aksiyonlar: `buzzer`, `light`, `emergency` |

---

### Vardiya Yönetimi

#### `GET /api/shift/current`
Şu anda aktif vardiyayı ve o vardiyada biriken dozu döndürür.

```json
{
  "active": true,
  "shift_name": "Hafta İçi",
  "shift_dose": 1.114
}
```

- `active: false` → Şu an tanımlı hiçbir vardiya çalışmıyor.
- `shift_dose` → Bu vardiyanın başından itibaren biriken doz (µSv).

#### `GET /api/shift/history?days=<n>`
Son N günün tamamlanmış vardiya doz kayıtları.

**`days` parametresi:** Tamsayı, varsayılan `7`

```json
[
  {
    "shift_name": "Hafta İçi",
    "date": "2026-04-03",
    "start_time": "08:00",
    "end_time": "17:30",
    "dose": 1.114
  },
  {
    "shift_name": "Hafta İçi (Akşam)",
    "date": "2026-04-03",
    "start_time": "17:30",
    "end_time": "08:00",
    "dose": 0.923
  }
]
```

> **Not:** Gece vardiyaları (bitiş < başlangıç, ör. 17:30–08:00) vardiyayı başlatan günün tarihi ile kaydedilir.

---

## Cihaz Kimliği

### `GET /api/device`
Cihaz tanımlama bilgilerini döndürür. Manager'ın başlangıçta cihazı kaydetmesi için kullanın.

```json
{
  "device_name": "GammaScout-01",
  "device_location": "Reaktör Binası - Kat 2",
  "device_serial": "GS-0042"
}
```

> `device_serial` cihaz bağlandığında GammaScout'tan otomatik okunur. Henüz okunmamışsa boş string döner.

---

## Ayar Yönetimi

Tüm ayar endpoint'leri API key ile korunur. `PUT /api/settings` ayrıca admin cookie veya API key gerektirir.

### `GET /api/settings`
Cihazın tüm ayarlarını döndürür.

```json
{
  "device_name": "GammaScout-01",
  "device_location": "Reaktör Binası - Kat 2",
  "device_serial": "GS-0042",
  "sampling_interval": "10",
  "threshold_high": "0.5",
  "threshold_high_high": "1.0",
  "threshold_high_duration": "120",
  "threshold_high_high_duration": "15",
  "calibration_factor": "1.0",
  "alarm_high_actions": "buzzer,light",
  "alarm_high_high_actions": "buzzer,light,emergency",
  "alarm_email_enabled": "false",
  "alarm_email_to": "",
  "smtp_host": "",
  "smtp_port": "587",
  "smtp_user": "",
  "smtp_pass": "",
  "gpio_buzzer_pin": "17",
  "gpio_light_pin": "27",
  "gpio_emergency_pin": "22",
  "remote_log_enabled": "false",
  "remote_log_url": "",
  "remote_log_api_key": "",
  "msg_service_url": "",
  "msg_service_api_key": "",
  "msg_service_mail_enabled": "false",
  "msg_service_wa_enabled": "false",
  "msg_service_reply_to": "",
  "msg_service_high_mail_to": "",
  "msg_service_high_wa_to": "",
  "msg_service_high_high_mail_to": "",
  "msg_service_high_high_wa_to": "",
  "shifts": "[{...}]"
}
```

> Tüm değerler string olarak saklanır. Sayısal alanları okurken `float()`/`int()` ile dönüştürün.

### `PUT /api/settings`
Bir veya birden fazla ayarı günceller. Yalnızca gönderilen anahtarlar değişir.

**İstek gövdesi:**
```json
{
  "threshold_high": "0.6",
  "threshold_high_duration": "90",
  "device_location": "Reaktör Binası - Kat 3"
}
```

**Yanıt:**
```json
{"status": "ok"}
```

### Ayar Anahtarları Referansı

| Anahtar | Tip | Açıklama |
|---|---|---|
| `device_name` | string | Cihaz görünen adı |
| `device_location` | string | Cihazın fiziksel konumu |
| `device_serial` | string | Cihaz seri numarası (GammaScout'tan otomatik okunur) |
| `sampling_interval` | int (sn) | Okuma aralığı (varsayılan: `10`) |
| `calibration_factor` | float | Kalibrasyon çarpanı (varsayılan: `1.0`) |
| `threshold_high` | float (µSv/h) | HIGH alarm eşiği |
| `threshold_high_high` | float (µSv/h) | HIGH-HIGH alarm eşiği |
| `threshold_high_duration` | int (sn) | HIGH alarm tetikleme süresi |
| `threshold_high_high_duration` | int (sn) | HIGH-HIGH alarm tetikleme süresi |
| `alarm_high_actions` | string | HIGH alarm aksiyonları: `buzzer,light,emergency` (virgülle) |
| `alarm_high_high_actions` | string | HIGH-HIGH alarm aksiyonları |
| `gpio_buzzer_pin` | int | BCM pin numarası — buzzer |
| `gpio_light_pin` | int | BCM pin numarası — ışık |
| `gpio_emergency_pin` | int | BCM pin numarası — acil çıkış |
| `alarm_email_enabled` | `"true"` \| `"false"` | SMTP e-posta bildirimi |
| `alarm_email_to` | string | Alarm e-posta alıcısı |
| `smtp_host` / `smtp_port` / `smtp_user` / `smtp_pass` | string | SMTP bağlantı bilgileri |
| `remote_log_enabled` | `"true"` \| `"false"` | Uzak log iletimi |
| `remote_log_url` | string | Uzak log endpoint URL'i |
| `remote_log_api_key` | string | Uzak log API anahtarı |
| `msg_service_url` | string | msgService base URL |
| `msg_service_api_key` | string | msgService API anahtarı |
| `msg_service_mail_enabled` | `"true"` \| `"false"` | msgService e-posta bildirimi |
| `msg_service_wa_enabled` | `"true"` \| `"false"` | msgService WhatsApp bildirimi |
| `msg_service_reply_to` | string | E-posta reply-to adresi |
| `msg_service_high_mail_to` | string | HIGH alarm e-posta alıcıları (virgülle) |
| `msg_service_high_wa_to` | string | HIGH alarm WhatsApp numaraları (virgülle) |
| `msg_service_high_high_mail_to` | string | HIGH-HIGH alarm e-posta alıcıları |
| `msg_service_high_high_wa_to` | string | HIGH-HIGH alarm WhatsApp numaraları |
| `shifts` | JSON string | Vardiya tanımları (bkz. aşağıda) |

### Vardiya Tanımları (`shifts`)

`shifts` ayarı, JSON dizisi içeren bir string olarak saklanır. `PUT /api/settings` ile güncellenirken JSON'u string'e serialize edin.

```json
[
  {
    "id": "hafta_ici",
    "name": "Hafta İçi",
    "days": [1, 2, 3, 4, 5],
    "start": "08:00",
    "end": "17:30"
  },
  {
    "id": "hafta_ici_aksam",
    "name": "Hafta İçi (Akşam)",
    "days": [1, 2, 3, 4, 5],
    "start": "17:30",
    "end": "08:00"
  }
]
```

| Alan | Açıklama |
|---|---|
| `id` | Benzersiz tanımlayıcı (slug formatı önerilir) |
| `name` | Görünen ad |
| `days` | ISO hafta günleri: 1=Pzt … 5=Cum, 6=Cmt, 7=Paz |
| `start` | Başlangıç saati `HH:MM` |
| `end` | Bitiş saati `HH:MM` — `end < start` ise gece vardiyası |

**Python örneği — ayar yazma:**
```python
import json
import httpx

def set_shifts(device_ip: str, shifts: list[dict]):
    url = f"http://{device_ip}:8090/api/settings"
    httpx.put(url, json={"shifts": json.dumps(shifts)})
```

---

## WebSocket — Gerçek Zamanlı Veri

> **Not:** WebSocket endpoint'i API key gerektirmez — push-only olduğu için muaftır.

### Bağlantı

```
ws://<cihaz-ip>:8090/ws/live
wss://<cihaz-ip>:8090/ws/live   (SSL aktifse)
```

### Mesaj Formatı

Bağlantı kurulduktan sonra cihaz, her yeni ölçümde aşağıdaki JSON'u push eder:

```json
{
  "type": "reading",
  "timestamp": "2026-04-03T14:32:10.123456+00:00",
  "dose_rate": 0.142,
  "cumulative_dose": 4521.338,
  "shift_name": "Hafta İçi",
  "shift_dose": 1.114,
  "shift_active": true,
  "alarm_pending": false,
  "alarm_pending_level": null,
  "alarm_pending_elapsed": 0,
  "alarm_pending_duration": 0
}
```

`type` alanı şu an yalnızca `"reading"` değerini alır; ileride genişletilebilir.

### Örnek (Python)

```python
import asyncio
import websockets
import json

async def listen(device_ip: str):
    uri = f"ws://{device_ip}:8090/ws/live"
    async with websockets.connect(uri) as ws:
        async for raw in ws:
            data = json.loads(raw)
            print(f"[{data['timestamp']}] {data['dose_rate']:.3f} µSv/h")

asyncio.run(listen("192.168.1.100"))
```

---

## Çoklu Cihaz Mimarisi

Manager, N cihazı aynı anda izlemek için her cihaza bağımsız bağlantı açmalıdır.

### Önerilen Yaklaşım

```
Manager
 ├── Cihaz 1 (192.168.1.100:8090)  ← WebSocket bağlantısı
 ├── Cihaz 2 (192.168.1.101:8090)  ← WebSocket bağlantısı
 └── Cihaz N (...)                  ← WebSocket bağlantısı
```

- Her cihaz için ayrı bir WebSocket task/goroutine/thread açın.
- Cihaz listesini manager konfigürasyonunda tutun (IP, isim, lokasyon).
- Bağlantı koptuğunda (cihaz kapandı, ağ kesintisi) exponential backoff ile yeniden bağlanın.
- REST polling'i yalnızca geçmiş veri veya WebSocket bağlantısı kurulamayan durum için kullanın.

### Cihaz Kimliği

Her cihaz `GET /api/device` endpoint'i ile tanımlanabilir — cihaz adı, lokasyon ve seri numarası döner. Cihazı IP/hostname + seri numarası ile ayırt edin.

---

## Hata Durumları

| Durum | Belirti | Önerilen Aksiyon |
|---|---|---|
| Cihaz erişilemez | HTTP timeout / bağlantı reddedildi | `status = OFFLINE` olarak işaretle, retry uygula |
| Dedektör bağlı değil | `connected: false` | Uyarı göster, alarm üretme |
| Ölçüm gelmiyor | `timestamp` eskimiş (> 60sn) | Cihazı yeniden sorgula / WS yeniden bağlan |
| Alarm aktif | `alarm_pending: true` veya `/api/alarms` kayıt var | Manager'da bildirim üret |

---

## Özet: Hangi Endpoint, Ne Zaman

| Amaç | Endpoint | Yöntem | Auth |
|---|---|---|---|
| Canlı doz takibi | `ws://.../ws/live` | WebSocket push | Yok |
| Cihaz ayakta mı? | `GET /api/health` | 30sn polling | API key |
| Cihaz bilgileri | `GET /api/device` | İstek üzerine | API key |
| Anlık değer (fallback) | `GET /api/current` | 10–30sn polling | API key |
| Son 1/6/24 saat grafiği | `GET /api/readings?last=1h` | İstek üzerine | API key |
| Günlük/dönemsel özet | `GET /api/period-doses` | Dakikada bir polling | API key |
| Alarm geçmişi | `GET /api/alarms?last=24h` | Periyodik veya event-driven | API key |
| Vardiya doz özeti | `GET /api/shift/history?days=7` | Vardiya değişiminde | API key |
| Aktif vardiya dozu | `GET /api/shift/current` | 60sn polling veya WS'den | API key |
| Tüm ayarları oku | `GET /api/settings` | İstek üzerine | API key |
| Ayar güncelle | `PUT /api/settings` | İstek üzerine | API key + admin |
