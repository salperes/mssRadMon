# msgService Entegrasyon Tasarımı

**Tarih:** 2026-04-01  
**Kapsam:** mssRadMon alarm sistemine msgService üzerinden e-posta ve WhatsApp bildirimi eklenmesi

---

## Genel Bakış

Mevcut SMTP e-posta bildirimi korunur. Yanına `app/msg_service.py` modülü eklenerek alarm tetiklendiğinde msgService REST API'si üzerinden e-posta ve/veya WhatsApp gönderilebilir. Her alarm seviyesi (HIGH, HIGH-HIGH) için alıcılar ve kanallar bağımsız olarak admin panelinden yapılandırılır.

---

## Mimari

### Yeni Modül: `app/msg_service.py`

- stdlib `urllib.request` kullanır (`requests` bağımlılığı eklenmez)
- İki public sync fonksiyon: `send_mail(...)` ve `send_whatsapp(...)`
- Config'den URL, API key, enable/disable, alıcı listelerini okur
- Hata durumunda `None` döner, exception fırlatmaz — uygulama çökmez
- SSL doğrulaması devre dışı (iç ağ CA sorunu, msgService dokümanıyla tutarlı)
- `asyncio.get_event_loop().run_in_executor(None, ...)` ile async context'ten çağrılır (SMTP ile aynı pattern)

### `app/alarm.py` Değişikliği

`_trigger_alarm` metoduna mevcut `_send_email` bloğunun yanına iki yeni blok eklenir:

```python
# msgService e-posta (mevcut SMTP'ye dokunulmaz)
await self._send_msgservice_mail(level, dose_rate)
# msgService WhatsApp
await self._send_msgservice_wa(level, dose_rate)
```

`_send_msgservice_mail` ve `_send_msgservice_wa` metodları `msg_service.py` fonksiyonlarını executor üzerinden çağırır, ilgili config key'lerini okur.

### `app/routers/admin.py` Değişikliği

Üç yeni endpoint:

| Endpoint | Method | Açıklama |
|----------|--------|----------|
| `/api/msgservice/health` | GET | msgService `/api/health` proxy — versiyon, kuyruk, smtp, wa durumu |
| `/api/msgservice/test-mail` | POST | `{level: "high"\|"high_high"}` — o seviyenin alıcılarına test maili |
| `/api/msgservice/test-wa` | POST | `{level: "high"\|"high_high"}` — o seviyenin numaralarına test WA |

---

## Config Keys

`app/config.py` DEFAULTS'a eklenir:

| Key | Varsayılan | Açıklama |
|-----|-----------|----------|
| `msg_service_url` | `http://192.168.88.112:3501` | msgService base URL |
| `msg_service_api_key` | `""` | API key (msgService admin panelinden "mssradmon" uygulaması için oluşturulur) |
| `msg_service_mail_enabled` | `"false"` | Global mail toggle |
| `msg_service_wa_enabled` | `"false"` | Global WA toggle |
| `msg_service_reply_to` | `""` | Reply-To adresi |
| `msg_service_high_mail_to` | `""` | HIGH alarm mail alıcıları (virgülle ayrılmış) |
| `msg_service_high_wa_to` | `""` | HIGH alarm WA numaraları (virgülle ayrılmış) |
| `msg_service_high_high_mail_to` | `""` | HIGH-HIGH alarm mail alıcıları (virgülle ayrılmış) |
| `msg_service_high_high_wa_to` | `""` | HIGH-HIGH alarm WA numaraları (virgülle ayrılmış) |

**Kanal aktiflik kuralı:** Global toggle `true` VE ilgili alıcı listesi dolu ise o kanal çalışır.

Mevcut `PUT /api/settings` endpoint'i değişmez — yeni key'ler de aynı mekanizmayla kaydedilir.

---

## Admin Panel (templates/admin.html)

Mevcut "E-posta Bildirimleri" kartının altına yeni **"msgService Bildirimleri"** kartı eklenir:

**Genel Ayarlar:**
- msgService URL
- API Key
- Mail Bildirimleri (toggle)
- WhatsApp Bildirimleri (toggle)
- Reply-To

**HIGH Seviye:**
- Mail alıcıları (textarea, virgülle)
- WA numaraları (textarea, virgülle, E.164 formatsız — ör. `905551234567`)

**HIGH-HIGH Seviye:**
- Mail alıcıları (textarea, virgülle)
- WA numaraları (textarea, virgülle, E.164 formatsız — ör. `905551234567`)

**Eylem Butonları:**
- "Bağlantı Testi" → `GET /api/msgservice/health` → versiyon + kuyruk durumu inline gösterilir
- "Test Mail (HIGH)" → `POST /api/msgservice/test-mail {level:"high"}`
- "Test Mail (HIGH-HIGH)" → `POST /api/msgservice/test-mail {level:"high_high"}`
- "Test WA (HIGH)" → `POST /api/msgservice/test-wa {level:"high"}`
- "Test WA (HIGH-HIGH)" → `POST /api/msgservice/test-wa {level:"high_high"}`

---

## E-posta İçeriği

msgService `"alert"` template kullanılır. Mail gövdesi:

```
Radyasyon alarmi tetiklendi.

Seviye : HIGH / HIGH-HIGH
Doz Hizi: X.XXX µSv/h
Zaman  : HH:MM - DD/MM/YYYY
Cihaz  : <device_name>
Lokasyon: <device_location>
```

`metadata.source = "mssradmon"`, `metadata.entityType = "alarm"`, `metadata.entityId = level.value`

---

## WhatsApp İçeriği

Düz metin mesajı (medya yok):

```
[mssRadMon] ALARM HIGH-HIGH
Doz: X.XXX µSv/h | HH:MM - DD/MM/YYYY
Cihaz: <device_name>
```

---

## Hata Yönetimi

- URL veya API key boşsa → sessizce atla, log.warning
- HTTP 4xx/5xx → log.error, `None` dön
- Bağlantı zaman aşımı (5s) → log.error, `None` dön
- Herhangi bir hata alarm tetiklenmesini engellemez (GPIO, SMTP hâlâ çalışır)

---

## Değişmeyen Bileşenler

- SMTP e-posta kodu (`_send_email`, `send_test_email`) — dokunulmaz
- Mevcut alarm eşik/süre mantığı — dokunulmaz
- GPIO çıkışları — dokunulmaz
- `PUT /api/settings` endpoint — dokunulmaz
- Veritabanı şeması — ek tablo/migration yok
