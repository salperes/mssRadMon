# msgService Entegrasyon Yönergesi

**Versiyon:** msgService 0.2.18+
**Prod URL:** `http://192.168.88.112:3501`
**Prod API Key:** Uygulamana ait key icin bkz. [API Key Tablosu](#api-key-tablosu)
**Swagger:** `http://192.168.88.112:3501/api/docs?key=fe1JHxiYtKpJrrSYuDuCN9Mw3Avygl0X`

---

## Genel Bakis

msgService, kurumsal uygulamalar icin merkezi e-posta ve WhatsApp gonderim servisidir.
REST API kabul eder, mesajlari DB kuyruguna alir ve asenkron olarak iletir.

**Ozellikler:**
- HTML/text e-posta (sablon destegi)
- Dosya eki (attachment) destegi
- iCal takvim daveti destegi (Outlook Accept/Decline/Tentative)
- Toplu (bulk) gonderim
- WhatsApp mesaj + medya gonderimi
- Mesaj durum takibi
- Rate limiting (100 istek/dakika per API key)

---

## API Key Tablosu (Prod)

| Uygulama     | API Key                                              |
|--------------|------------------------------------------------------|
| PDKS         | `pk_pdks_b2333c924fc4565bea4155f9e81fdf26`          |
| Portal       | `pk_portal_860b1b2f4e74e87e23e53192a21c0249`        |
| ReqMgmt      | `pk_reqmgmt_3be226857fb74e619a6c8656f5e3f6e1`       |
| TimeSheet    | `pk_timesheet_dca4d274bcd78f0100e0a549b303dc2c`     |
| mssFilo      | `pk_filo_608388698e19f718947e71948c56b4e4`          |
| HiringPortal | `pk_hiringportal_6f5ac4b3994917fd948e0a474f313bab`  |

Yeni bir uygulama icin msgService admin panelinden (http://192.168.88.112:3501) API key olusturulur.
API key olusturulurken **fromName** alani belirlenerek gonderici adi ozellestirilebilir (orn. `"PORTAL MSS"`).

---

## Endpoints

| Endpoint              | Method | Auth        | Aciklama                              |
|-----------------------|--------|-------------|---------------------------------------|
| `/api/send`           | POST   | X-API-Key   | E-posta kuyruga ekle                  |
| `/api/send/bulk`      | POST   | X-API-Key   | Toplu e-posta kuyruga ekle (max 100)  |
| `/api/status/:id`     | GET    | X-API-Key   | E-posta durum sorgula                 |
| `/api/wa/send`        | POST   | X-API-Key   | WhatsApp mesaji gonder                |
| `/api/wa/status/:id`  | GET    | X-API-Key   | WhatsApp mesaj durumu sorgula         |
| `/api/health`         | GET    | Yok         | Servis durumu / versiyon              |

---

## 1. E-Posta Gonderme

### Request

```
POST http://192.168.88.112:3501/api/send
Content-Type: application/json
X-API-Key: pk_<appname>_<hex>
```

```json
{
  "to": ["alici@msspektral.com"],
  "cc": ["kopya@msspektral.com"],
  "bcc": ["gizlikopya@msspektral.com"],
  "subject": "Konu basligi",
  "body": "<p>HTML icerik</p>",
  "bodyType": "html",
  "replyTo": "noreply@msspektral.com",
  "template": "default",
  "attachments": [
    {
      "filename": "rapor.pdf",
      "content": "base64encodeddata...",
      "contentType": "application/pdf"
    }
  ],
  "icalEvent": "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n...\r\nEND:VCALENDAR",
  "metadata": {
    "source": "my-app",
    "entityType": "invoice",
    "entityId": "123"
  }
}
```

### Alan Aciklamalari

| Alan          | Zorunlu | Aciklama                                                       |
|---------------|---------|----------------------------------------------------------------|
| `to`          | Evet    | Alici listesi (array of string, min 1)                         |
| `cc`          | Hayir   | CC listesi (array of string)                                   |
| `bcc`         | Hayir   | BCC listesi (array of string)                                  |
| `subject`     | Evet    | Mail konusu (max 500 karakter)                                 |
| `body`        | Evet    | Mail govdesi (HTML veya duz metin)                             |
| `bodyType`    | Hayir   | `"html"` (varsayilan) veya `"text"`                            |
| `replyTo`     | Hayir   | Reply-To adresi                                                |
| `template`    | Hayir   | `"default"`, `"notification"`, `"alert"`, `"raw"` (max 100 kr)|
| `attachments` | Hayir   | Dosya ekleri (asagidaki tabloya bkz.)                          |
| `icalEvent`   | Hayir   | iCalendar string (Outlook davet butonlari icin)                |
| `metadata`    | Hayir   | Izleme icin serbest key-value (admin panelde gorunur)          |

### Attachment Alanlari

| Alan          | Zorunlu | Aciklama                               |
|---------------|---------|----------------------------------------|
| `filename`    | Evet    | Dosya adi (orn. `"rapor.pdf"`)         |
| `content`     | Evet    | Base64 encoded dosya icerigi           |
| `contentType` | Hayir   | MIME tipi (orn. `"application/pdf"`)   |

**Limitler:** Dosya basi max 10 MB, mesaj basi toplam max 25 MB.

### Template Secenekleri

| Template         | Aciklama                                 |
|------------------|------------------------------------------|
| `"default"`      | Kurumsal sablon (logo, footer)           |
| `"notification"` | Bildirim sablonu                         |
| `"alert"`        | Uyari/alarm sablonu                      |
| `"raw"`          | Sablonsuz, sadece body icerigi           |

### Response (basari — HTTP 202)

```json
{
  "success": true,
  "messageId": "uuid",
  "status": "queued",
  "queuedAt": "2026-04-01T12:00:00Z"
}
```

### Response (hata)

```json
{
  "success": false,
  "error": "Validation error",
  "details": ["'to' must contain at least one recipient"]
}
```

| HTTP | Anlam                                    |
|------|------------------------------------------|
| 400  | Validasyon hatasi                        |
| 401  | Gecersiz veya eksik API key              |
| 429  | Rate limit asildi (100 istek/dk)         |
| 500  | Sunucu hatasi                            |

---

## 2. Toplu E-Posta Gonderme (Bulk)

```
POST http://192.168.88.112:3501/api/send/bulk
Content-Type: application/json
X-API-Key: pk_<appname>_<hex>
```

```json
{
  "messages": [
    {
      "to": ["alici1@msspektral.com"],
      "subject": "Bildirim 1",
      "body": "<p>Icerik 1</p>",
      "template": "default"
    },
    {
      "to": ["alici2@msspektral.com"],
      "subject": "Bildirim 2",
      "body": "<p>Icerik 2</p>",
      "template": "notification"
    }
  ],
  "metadata": { "source": "my-app" }
}
```

**Limit:** 1-100 mesaj per istek.

### Response (HTTP 202)

```json
{
  "success": true,
  "batchId": "uuid",
  "queued": 2,
  "messageIds": ["uuid1", "uuid2"]
}
```

---

## 3. E-Posta Durum Sorgulama

```
GET http://192.168.88.112:3501/api/status/{messageId}
X-API-Key: pk_<appname>_<hex>
```

### Response

```json
{
  "messageId": "uuid",
  "status": "queued|processing|sent|failed",
  "to": ["alici@msspektral.com"],
  "subject": "Konu",
  "queuedAt": "2026-04-01T12:00:00Z",
  "sentAt": "2026-04-01T12:00:30Z",
  "failedAt": null,
  "retryCount": 0,
  "errorMessage": null,
  "source": "my-app",
  "attachments": [
    { "filename": "rapor.pdf", "contentType": "application/pdf", "sizeBytes": 102400 }
  ]
}
```

**Durum gecisleri:** `queued` -> `processing` -> `sent` | `failed`
Basarisiz mesajlar max 3 kez tekrar denenir (exponential backoff: 2^n * 30sn).

---

## 4. WhatsApp Mesaj Gonderme

```
POST http://192.168.88.112:3501/api/wa/send
Content-Type: application/json
X-API-Key: pk_<appname>_<hex>
```

### Metin Mesaji

```json
{
  "phone": "905551234567",
  "body": "Mesaj metni (max 4096 karakter)",
  "metadata": { "source": "my-app", "entityType": "order", "entityId": "42" }
}
```

### Medya Mesaji

```json
{
  "phone": "905551234567",
  "body": "Resim aciklamasi",
  "mediaPath": "/path/to/file.jpg",
  "mediaType": "image",
  "mediaMimeType": "image/jpeg",
  "mediaFilename": "photo.jpg",
  "metadata": { "source": "my-app" }
}
```

### Alan Aciklamalari

| Alan            | Zorunlu | Aciklama                                          |
|-----------------|---------|---------------------------------------------------|
| `phone`         | Evet    | Telefon numarasi (E.164 formati, + olmadan)       |
| `body`          | *       | Mesaj metni (max 4096 karakter)                   |
| `mediaPath`     | *       | Medya dosya yolu                                  |
| `mediaType`     | Hayir   | `image`, `video`, `audio`, `document`             |
| `mediaMimeType` | Hayir   | MIME tipi (orn. `"image/jpeg"`)                   |
| `mediaFilename` | Hayir   | Dosya adi                                         |
| `metadata`      | Hayir   | Izleme icin serbest key-value                     |

\* `body` veya `mediaPath` alanlarindan en az biri zorunlu.

### Response (HTTP 202)

```json
{
  "success": true,
  "messageId": "mongodb_id",
  "status": "queued",
  "queuedAt": "2026-04-01T12:00:00Z"
}
```

---

## 5. WhatsApp Durum Sorgulama

```
GET http://192.168.88.112:3501/api/wa/status/{messageId}
X-API-Key: pk_<appname>_<hex>
```

### Response

```json
{
  "messageId": "mongodb_id",
  "status": "queued|processing|sent|failed",
  "phone": "905551234567",
  "queuedAt": "2026-04-01T12:00:00Z",
  "sentAt": "2026-04-01T12:00:30Z",
  "failedAt": null,
  "retryCount": 0,
  "errorMessage": null,
  "waMessageId": "true_1234567890@c.us_ABCD1234",
  "source": "my-app"
}
```

---

## 6. Servis Durumu Kontrolu

```
GET http://192.168.88.112:3501/api/health
```

```json
{
  "status": "ok|degraded",
  "version": "0.2.18",
  "queue": { "pending": 0, "processing": 0, "failed": 0 },
  "smtp": "connected|disconnected",
  "db": "connected|disconnected",
  "whatsapp": "connected|disconnected",
  "uptime": 3600
}
```

---

## iCal Takvim Daveti Ornegi

Outlook native Accept/Decline/Tentative butonlari icin `icalEvent` alani kullanilir:

```json
{
  "to": ["katilimci@msspektral.com"],
  "subject": "Toplanti Daveti - Sprint Planning",
  "body": "<p>Sprint Planning toplantisina davetlisiniz.</p>",
  "template": "default",
  "icalEvent": "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//MyApp//TR\r\nMETHOD:REQUEST\r\nBEGIN:VEVENT\r\nUID:unique-event-id@myapp\r\nDTSTAMP:20260401T120000Z\r\nDTSTART:20260405T090000Z\r\nDTEND:20260405T100000Z\r\nSUMMARY:Sprint Planning\r\nLOCATION:Toplanti Odasi 3\r\nORGANIZER;CN=Organizator:mailto:org@msspektral.com\r\nATTENDEE;RSVP=TRUE;CN=Katilimci:mailto:katilimci@msspektral.com\r\nEND:VEVENT\r\nEND:VCALENDAR"
}
```

---

## Python Entegrasyonu (Referans Implementasyon)

HiringPortal'daki `utils/msg_service.py` dogrudan kopyalanarak kullanilabilir.
Bu modul asagidaki mimariye sahiptir:

### 1. Ayarlarin DB'de Saklanmasi

Sabit hardcode yerine ayarlar uygulamanin DB'sindeki `system_settings` tablosunda tutulur:

```
msg_service_url          -> http://192.168.88.112:3501
msg_service_api_key      -> pk_<appname>_<hex>
msg_service_mail_enabled -> true / false
msg_service_wa_enabled   -> true / false
msg_service_reply_to     -> noreply@msspektral.com
msg_service_cc           -> cc1@msspektral.com,cc2@msspektral.com
```

Bu sayede admin, uygulamayi yeniden deploy etmeden servisi enable/disable edebilir.

### 2. Temel Kullanim

```python
from utils.msg_service import send_mail, send_whatsapp

# E-posta gonder
result = send_mail(
    to=["alici@msspektral.com"],
    cc=["kopya@msspektral.com"],
    bcc=["gizli@msspektral.com"],
    subject="Bildirim Basligi",
    body="<p>Icerik</p>",
    template="default",
    attachments=[{
        "filename": "rapor.pdf",
        "content": base64.b64encode(open("rapor.pdf", "rb").read()).decode(),
        "contentType": "application/pdf"
    }],
    metadata={"source": "my-app", "entityType": "order", "entityId": "42"}
)

if result:
    print(f"Kuyruga eklendi: {result['messageId']}")
else:
    print("Gonderim devre disi veya baglanti hatasi")

# WhatsApp gonder
send_whatsapp(
    phone="905551234567",
    body="Siparisiniz teslim edildi.",
    metadata={"source": "my-app"}
)
```

`send_mail` / `send_whatsapp`:
- `msg_service_mail_enabled` / `msg_service_wa_enabled` `false` ise hicbir sey yapmadan `None` doner
- URL veya API key eksikse `None` doner
- Baglanti hatasi veya HTTP hatasi olursa `None` doner (uygulama cokmez)

### 3. SSL Notu

Ic ag CA sertifikasinda key usage extension sorunu var; Python/OpenSSL TLS dogrulamasini reddediyor.
Bu nedenle SSL dogrulamasi devre disi birakilmistir:

```python
import ssl
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE
```

Tum `urllib.request.urlopen` cagrilarinda `context=_ssl_ctx` gecirilmelidir.

### 4. `requests` Kutuphanesi Kullananlar Icin

```python
import requests
import base64

response = requests.post(
    "http://192.168.88.112:3501/api/send",
    json={
        "to": ["alici@msspektral.com"],
        "subject": "Test",
        "body": "<p>Merhaba</p>",
        "bodyType": "html",
        "template": "default",
        "attachments": [{
            "filename": "dosya.pdf",
            "content": base64.b64encode(open("dosya.pdf", "rb").read()).decode(),
            "contentType": "application/pdf"
        }],
        "metadata": {"source": "my-app"}
    },
    headers={"X-API-Key": "pk_myapp_abc123"},
    timeout=5,
    verify=False   # Ic ag CA sorunu
)
response.raise_for_status()
data = response.json()
# data["messageId"], data["status"]
```

### 5. Durum Sorgulama

```python
response = requests.get(
    f"http://192.168.88.112:3501/api/status/{message_id}",
    headers={"X-API-Key": "pk_myapp_abc123"},
    timeout=5,
    verify=False
)
data = response.json()
# data["status"] -> "queued", "processing", "sent", "failed"
```

---

## Node.js / JavaScript Entegrasyonu

### E-posta Gonderme

```javascript
const fs = require('fs');

async function sendMail({ to, subject, body, cc, bcc, template = 'default', attachments, icalEvent, metadata = {} }) {
  const res = await fetch('http://192.168.88.112:3501/api/send', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': process.env.MSG_SERVICE_API_KEY,
    },
    body: JSON.stringify({
      to: Array.isArray(to) ? to : [to],
      cc: cc || [],
      bcc: bcc || [],
      subject,
      body,
      bodyType: 'html',
      template,
      attachments,
      icalEvent,
      metadata,
    }),
  });
  if (!res.ok) throw new Error(`msgService HTTP ${res.status}`);
  return res.json(); // { success, messageId, status, queuedAt }
}

// Ornek: ek dosyali mail
const attachment = {
  filename: 'rapor.pdf',
  content: fs.readFileSync('rapor.pdf').toString('base64'),
  contentType: 'application/pdf',
};
await sendMail({
  to: 'alici@msspektral.com',
  subject: 'Aylik Rapor',
  body: '<p>Ekte aylik raporu bulabilirsiniz.</p>',
  attachments: [attachment],
  metadata: { source: 'my-app', entityType: 'report', entityId: '2026-03' },
});
```

### WhatsApp Gonderme

```javascript
async function sendWhatsApp({ phone, body, mediaPath, mediaType, metadata = {} }) {
  const res = await fetch('http://192.168.88.112:3501/api/wa/send', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': process.env.MSG_SERVICE_API_KEY,
    },
    body: JSON.stringify({ phone, body, mediaPath, mediaType, metadata }),
  });
  if (!res.ok) throw new Error(`msgService WA HTTP ${res.status}`);
  return res.json(); // { success, messageId, status, queuedAt }
}
```

### Durum Sorgulama

```javascript
async function checkStatus(messageId) {
  const res = await fetch(`http://192.168.88.112:3501/api/status/${messageId}`, {
    headers: { 'X-API-Key': process.env.MSG_SERVICE_API_KEY },
  });
  return res.json(); // { messageId, status, sentAt, failedAt, ... }
}
```

---

## C# / .NET Entegrasyonu

```csharp
using System.Net.Http;
using System.Net.Http.Json;

public class MsgServiceClient
{
    private readonly HttpClient _http;
    private readonly string _apiKey;

    public MsgServiceClient(string baseUrl, string apiKey)
    {
        _http = new HttpClient { BaseAddress = new Uri(baseUrl) };
        _apiKey = apiKey;
    }

    public async Task<MsgResult> SendMailAsync(
        string[] to, string subject, string body,
        string[] cc = null, string[] bcc = null,
        string template = "default",
        List<Attachment> attachments = null,
        Dictionary<string, string> metadata = null)
    {
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/send");
        request.Headers.Add("X-API-Key", _apiKey);
        request.Content = JsonContent.Create(new
        {
            to,
            cc = cc ?? Array.Empty<string>(),
            bcc = bcc ?? Array.Empty<string>(),
            subject,
            body,
            bodyType = "html",
            template,
            attachments,
            metadata
        });

        var response = await _http.SendAsync(request);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<MsgResult>();
    }

    public async Task<MsgResult> SendWhatsAppAsync(
        string phone, string body,
        Dictionary<string, string> metadata = null)
    {
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/wa/send");
        request.Headers.Add("X-API-Key", _apiKey);
        request.Content = JsonContent.Create(new { phone, body, metadata });

        var response = await _http.SendAsync(request);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<MsgResult>();
    }

    public async Task<StatusResult> CheckStatusAsync(string messageId)
    {
        var request = new HttpRequestMessage(HttpMethod.Get, $"/api/status/{messageId}");
        request.Headers.Add("X-API-Key", _apiKey);

        var response = await _http.SendAsync(request);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<StatusResult>();
    }
}

public record MsgResult(bool Success, string MessageId, string Status, DateTime QueuedAt);
public record Attachment(string Filename, string Content, string ContentType);
public record StatusResult(string MessageId, string Status, DateTime? SentAt, DateTime? FailedAt, int RetryCount, string ErrorMessage);
```

---

## Admin Paneli Arayuzu (Opsiyonel)

Uygulamanin kendi admin sayfasinda msgService ayarlarini yonetmek icin su ozellikler eklenebilir:

1. **Ayar formu:** URL, API key, enabled toggle, replyTo, CC alanlari -> `system_settings` tablosuna kaydet
2. **Baglanti testi:** `/api/health` GET -> versiyon/durum goster
3. **Test maili:** Formdaki bilgilerle `/api/send` POST
4. **Test WhatsApp:** Formdaki bilgilerle `/api/wa/send` POST

HiringPortal'da bu sayfa `handlers/system_settings.py` ve `templates/system_settings.html` altindadir; referans alinabilir.

---

## Kuyruk Davranisi

- **Islem araliği:** 10 saniyede bir (yapilandiriabilir)
- **Batch buyuklugu:** 5 mesaj/batch (yapilandiriabilir)
- **Max yeniden deneme:** 3 (yapilandiriabilir)
- **Yeniden deneme stratejisi:** Exponential backoff (2^n * 30 saniye)
- **Durum gecisleri:** `queued` -> `processing` -> `sent` | `failed`
- **Ayni anda islem:** PostgreSQL `FOR UPDATE SKIP LOCKED` ile concurrency guvenli

WhatsApp kuyruğu da ayni mantikla calisir, ancak WA client bagli olmalidir.

---

## Checklist — Yeni Uygulama Entegrasyonu

- [ ] `system_settings` tablosuna msg-service alanlari eklendi (yukaridaki 6 key)
- [ ] `utils/msg_service.py` modulu kopyalandi / adapt edildi (veya dil bazli client yazildi)
- [ ] Prod API key `msg_service_api_key` olarak DB'ye girildi
- [ ] `msg_service_url` = `http://192.168.88.112:3501` olarak ayarlandi
- [ ] `msg_service_mail_enabled` = `true` yapildi
- [ ] `metadata.source` alaninda uygulama adi belirtildi
- [ ] Test maili gonderildi ve admin panelde goruldu dogrulandi
- [ ] (Opsiyonel) WhatsApp entegrasyonu test edildi
- [ ] (Opsiyonel) Durum sorgulama (`/api/status/:id`) entegre edildi
