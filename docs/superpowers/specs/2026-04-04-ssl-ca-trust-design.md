# SSL / CA Trust — Tasarım Dokümanı

**Tarih:** 2026-04-04  
**Konu:** İntranet CA sertifikasını sisteme trust etme, CA sunucudan hostname bazlı SSL sertifikası talebi, uvicorn HTTPS geçişi  
**Durum:** Onaylandı

---

## Kapsam

1. CA sertifikasını sisteme güvenilir olarak ekle (`update-ca-certificates`)
2. CA sunucudan hostname bazlı sertifika talep et ve `data/ssl/` altına kaydet
3. Uvicorn'u SSL ile başlat — HTTPS aktif et
4. Admin panelde "SSL Yönetimi" bölümü

---

## 1. Veri Modeli

### Settings Tablosu — Yeni Anahtarlar

| Key | Varsayılan | Açıklama |
|-----|-----------|----------|
| `ca_server_url` | `""` | CA sunucu adresi (ör: `http://192.168.88.111:3020`) |
| `ca_api_key` | `""` | CA sunucuya erişim API key |
| `ssl_enabled` | `false` | HTTPS aktif mi |

`config.py` DEFAULTS'a üç anahtar eklenir.

### SSL Dosya Dizini

```
data/ssl/
  ca.crt        # CA sertifikası (trust + sertifika zinciri)
  server.key    # Private key (chmod 600)
  server.crt    # Signed sertifika
```

`data/ssl/` dizini yoksa endpoint'ler oluşturur.

---

## 2. Backend API Endpoint'leri

Tüm endpoint'ler admin cookie ile korunur (`require_admin`). API key dependency'sinden muaf — admin panel iç işlemleri.

### 2.1 `GET /api/ssl/status`

Mevcut SSL durumunu döndürür.

**Yanıt:**
```json
{
  "ca_trusted": true,
  "has_cert": true,
  "ssl_enabled": true,
  "expiry": "2028-02-21T00:00:00Z",
  "subject": "CN=mssradmon.mss.local",
  "ca_server": {
    "reachable": true,
    "initialized": true
  }
}
```

**Mantık:**
- `ca_trusted`: `/usr/local/share/ca-certificates/mss-ca.crt` dosyası var mı
- `has_cert`: `data/ssl/server.crt` ve `data/ssl/server.key` var mı
- `ssl_enabled`: settings'ten oku
- `expiry`, `subject`: `openssl x509` ile `data/ssl/server.crt`'den parse et
- `ca_server`: settings'teki `ca_server_url`'e `GET /api/ca/status` ile erişim testi (timeout 5s)

### 2.2 `POST /api/ssl/trust-ca`

CA sertifikasını CA sunucudan indirir ve sisteme güvenilir olarak ekler.

**Akış:**
1. `GET {ca_server_url}/api/ca/certificate` → PEM formatında CA sertifikası al
2. `data/ssl/ca.crt` olarak kaydet
3. `/usr/local/share/ca-certificates/mss-ca.crt` olarak kopyala (sudo gerekir)
4. `sudo update-ca-certificates` çalıştır

**Yanıt:**
```json
{ "ok": true, "message": "CA sertifikası güvenilir olarak eklendi" }
```

**sudo erişimi:** `mssadmin` kullanıcısı için sudoers'a passwordless kural eklenmeli:
```
mssadmin ALL=(ALL) NOPASSWD: /usr/sbin/update-ca-certificates
mssadmin ALL=(ALL) NOPASSWD: /bin/cp /home/mssadmin/mssRadMon/data/ssl/ca.crt /usr/local/share/ca-certificates/mss-ca.crt
```

### 2.3 `POST /api/ssl/request`

CA sunucudan hostname bazlı sertifika talep eder.

**Gövde:**
```json
{
  "hostname": "mssradmon.mss.local"
}
```

IP adresi SAN'a eklenmez. `ipAddress` alanı CA API'sine boş string olarak gönderilir.

**Akış:**
1. Settings'ten `ca_server_url` ve `ca_api_key` oku
2. `POST {ca_server_url}/api/certificates/request` çağır:
   ```json
   {
     "hostname": "mssradmon.mss.local",
     "ipAddress": "",
     "appName": "mssradmon"
   }
   ```
3. Yanıttan `key`, `cert`, `caCert` al
4. `data/ssl/server.key` yaz (chmod 600)
5. `data/ssl/server.crt` yaz
6. `data/ssl/ca.crt` güncelle (yanıttaki `caCert` ile)
7. Settings'te `ssl_enabled = true` yap
8. Systemd servisini SSL modunda restart et

**Yanıt:**
```json
{
  "ok": true,
  "message": "Sertifika yüklendi, HTTPS aktif — sayfa birkaç saniye içinde yeniden yüklenecek",
  "expiry": "2028-02-21T00:00:00Z"
}
```

---

## 3. HTTPS Geçişi — Uvicorn SSL

### Mekanizma

Sertifika başarıyla kaydedilince:
1. `ssl_enabled` ayarı `true` yapılır
2. Systemd unit dosyası (`/etc/systemd/system/mssradmon.service`) güncellenir — `ExecStart`'a `--ssl-keyfile` ve `--ssl-certfile` eklenir
3. `sudo systemctl daemon-reload && sudo systemctl restart mssradmon` çalıştırılır

**SSL modunda ExecStart:**
```
ExecStart=/home/mssadmin/mssRadMon/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8090 --ssl-keyfile /home/mssadmin/mssRadMon/data/ssl/server.key --ssl-certfile /home/mssadmin/mssRadMon/data/ssl/server.crt
```

**sudoers ek kurallar:**
```
mssadmin ALL=(ALL) NOPASSWD: /bin/cp /home/mssadmin/mssRadMon/systemd/mssradmon.service /etc/systemd/system/mssradmon.service
mssadmin ALL=(ALL) NOPASSWD: /bin/systemctl daemon-reload
mssadmin ALL=(ALL) NOPASSWD: /bin/systemctl restart mssradmon
```

### Uygulama Başlangıç Davranışı

`main.py` lifespan'da `ssl_enabled` kontrolü yapılmaz — SSL parametreleri uvicorn komut satırından gelir. Uygulama kodu SSL'den habersiz çalışır.

---

## 4. Admin Panel — SSL Yönetimi Bölümü

### Sidebar

`admin.html` sidebar'a yeni link: **SSL Yönetimi** → `#ssl`, `data-section="ssl"`

### Bölüm İçeriği (`sec-ssl`)

**Durum kartı** — üç satırlık durum göstergesi:
- `●` CA Güvenilir / Güvenilmiyor
- `●` Sertifika: Aktif (son geçerlilik: 21.02.2028) / Yok
- `●` HTTPS: Aktif / Pasif

**CA Ayarları kartı:**
- CA Sunucu URL — text input (`ca_server_url`)
- CA API Key — password input (`ca_api_key`)
- "Kaydet" butonu → `PUT /api/settings`
- "Bağlantı Testi" butonu → `GET /api/ssl/status` sonucundan `ca_server.reachable` göster
- "CA Sertifikasını Güvenilir Yap" butonu → `POST /api/ssl/trust-ca`

**Sertifika Talep kartı:**
- Hostname — text input (placeholder: `mssradmon.mss.local`)
- "Sertifika Talep Et" butonu → `POST /api/ssl/request`
- Sonuç mesajı
- Uyarı metni: "Sertifika talep edildiğinde servis yeniden başlatılır. Bağlantınız birkaç saniye kesilecektir."

### Viewer Rolü

viewer için tüm butonlar disabled, input'lar readonly.

---

## 5. Dosya Değişiklik Özeti

| Dosya | Değişiklik |
|-------|-----------|
| `app/config.py` | `ca_server_url`, `ca_api_key`, `ssl_enabled` DEFAULTS'a eklenir |
| `app/ssl.py` | **Yeni** — CA trust, sertifika talep, SSL durum kontrolü, servis restart fonksiyonları |
| `app/main.py` | SSL endpoint'leri eklenir (`/api/ssl/status`, `/api/ssl/trust-ca`, `/api/ssl/request`) |
| `app/templates/admin.html` | Sidebar "SSL Yönetimi" linki + `sec-ssl` bölümü |
| `app/static/js/admin.js` | SSL bölümü JS handler'ları |
| `systemd/mssradmon.service` | SSL modunda güncellenecek template |

---

## 6. Güvenlik

- `server.key` dosyası `chmod 600` ile korunur
- CA API key settings tablosunda saklanır (admin-only erişim)
- SSL endpoint'leri `require_admin` ile korunur
- `update-ca-certificates` ve `systemctl restart` için sınırlı sudoers kuralları — yalnızca belirli komutlar passwordless
