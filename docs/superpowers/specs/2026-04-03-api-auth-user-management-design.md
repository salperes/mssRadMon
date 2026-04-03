# API Key Auth + Kullanıcı Yönetimi — Tasarım Dokümanı

**Tarih:** 2026-04-03  
**Konu:** mssRadMon REST API key koruması, cihaz bilgisi endpoint'i, admin panel kullanıcı yönetimi  
**Durum:** Onaylandı

---

## Kapsam

1. Tüm `/api/*` endpoint'lerini tek bir API key ile koru
2. `GET /api/device` — cihaz kimlik bilgisi endpoint'i
3. Admin panelde "API Erişimi" bölümü — key üretimi ve yönetimi
4. Admin panelde "Kullanıcı Yönetimi" bölümü — rol tabanlı erişim, şifre değişikliği, kullanıcı ekleme/silme

---

## 1. API Key Kimlik Doğrulama

### Karar

- **Yöntem:** HTTP header `X-API-Key: <key>`
- **Kapsam:** Tüm `/api/*` endpoint'leri
- **Muafiyetler:** `/ws/live` (WebSocket, push-only), `/admin/*` HTML rotaları, `/admin/login`, `/admin/logout`
- **Tek key:** Cihaz başına bir API key; birden fazla key desteği yok
- **Uygulama:** FastAPI `Depends()` dependency — middleware değil

### Depolama

`settings` tablosuna yeni `api_key` anahtarı eklenir. Varsayılan: boş string.

- Key üretilmemişse: `503 Service Unavailable` — `{"detail": "API key henüz üretilmemiş"}`
- Key yanlışsa: `401 Unauthorized` — `{"detail": "Geçersiz API key"}`

### Yeni Dosya: `app/auth.py`

```python
from fastapi import Depends, HTTPException, Request

async def verify_api_key(request: Request):
    key = await request.app.state.config.get("api_key")
    if not key:
        raise HTTPException(503, "API key henüz üretilmemiş")
    if request.headers.get("X-API-Key") != key:
        raise HTTPException(401, "Geçersiz API key")
```

### Router Değişiklikleri

`api.py` ve `admin.py` router tanımlarına dependency eklenir:

```python
# api.py
router = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(verify_api_key)])

# admin.py
router = APIRouter(prefix="/api", tags=["admin"], dependencies=[Depends(verify_api_key)])
```

Key üretimi endpoint'i (`POST /api/apikey/generate`) bu dependency'den **muaf** tutulur — zaten admin cookie ile korunur. FastAPI'de `include_in_schema=False` + router dışında tanımlanarak muafiyet sağlanır.

### Key Üretimi Endpoint'i

```
POST /api/apikey/generate
```

- Cookie doğrulaması zorunlu (admin rolü)
- API key dependency'sinden muaf
- `secrets.token_hex(32)` ile 64 karakter hex key üretir
- `settings` tablosuna `api_key` olarak kaydeder
- Yanıtta tam key bir kez döner: `{"api_key": "a3f9..."}`

---

## 2. Cihaz Bilgisi Endpoint'i

### `GET /api/device`

API key korumalı. Manager uygulamasının başlangıçta cihazı tanımlaması için kullanılır.

**Yanıt:**
```json
{
  "device_name": "GammaScout-01",
  "device_location": "Reaktör Binası - Kat 2",
  "device_serial": "GS-0042"
}
```

| Alan | Kaynak | Açıklama |
|---|---|---|
| `device_name` | `settings.device_name` | Admin'den elle girilir |
| `device_location` | `settings.device_location` | Admin'den elle girilir |
| `device_serial` | `settings.device_serial` | GammaScout'tan otomatik, readonly |

`device_serial` henüz okunmamışsa boş string döner.

---

## 3. Admin Panel — "API Erişimi" Bölümü

### Sidebar

`admin.html` sidebar'a yeni link eklenir: `API Erişimi` → `#api-access`, `data-section="api-access"`

### Bölüm İçeriği (`sec-api-access`)

- **API Key alanı:** Input (readonly), key yoksa placeholder "Henüz üretilmemiş"
- **Maskeleme:** Key varsa ilk 4 karakter görünür, geri kalanı `•` — tam key gösterilmez
- **"Yeni Key Üret" butonu:** `POST /api/apikey/generate` çağırır, dönen key'i gösterir ve kopyalamaya hazır hale getirir
- **"Kopyala" butonu:** Tam key'i panoya kopyalar (tek seferlik reveal)
- **Uyarı metni:** "Yeni key üretildiğinde eski key geçersiz olur. Bağlı manager'ı güncellemeyi unutmayın."

### Davranış Akışı

1. Sayfa açılır → `GET /api/settings` ile key varlığı kontrol edilir
2. Key yoksa: boş alan + "Henüz üretilmemiş" bilgisi
3. Key varsa: maskelenmiş haliyle gösterilir
4. "Yeni Key Üret" tıklanır → confirm dialog → `POST /api/apikey/generate` → tam key gösterilir
5. "Kopyala" tıklanır → full key panoya yazılır, buton "Kopyalandı!" olur

---

## 4. Kullanıcı Yönetimi

### Veri Modeli

Yeni `users` tablosu `db.py` SCHEMA'ya eklenir:

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'viewer'))
);
```

**Şifre hash:** `hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 260000)` — salt olarak username kullanılır (ek tablo/sütun gerekmez).

### Migrasyon

`main.py` lifespan başlangıcında: `users` tablosu boşsa `mssadmin / Ankara12!` kaydı `admin` rolüyle eklenir. Hardcoded sabitler `main.py`'den kaldırılır.

### Rol Kuralları

| Eylem | admin | viewer |
|---|---|---|
| Dashboard (`/`) | ✓ | ✓ (login gerekmez) |
| Admin paneli görüntüleme | ✓ | ✓ |
| Ayar kaydetme (PUT) | ✓ | ✗ (403) |
| Kullanıcı yönetimi | ✓ | ✗ |
| Kendi şifresini değiştirme | ✓ | ✓ |

`viewer` için admin panelinde kaydet butonları `disabled` + gri renk; kullanıcı yönetimi bölümü gizli.

### Session Değişikliği

Mevcut HMAC cookie yapısı korunur. Cookie'ye rol eklenmez — her korumalı request'te DB'den rol sorgulanır:

```python
async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("mssradmon_session", "")
    username = _verify_cookie(token)
    if not username:
        raise HTTPException(401)
    user = await get_user_from_db(username)
    if not user:
        raise HTTPException(401)
    return user  # {"username": ..., "role": ...}

async def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403)
```

### Yeni API Endpoint'leri

Tüm endpoint'ler cookie auth ile korunur. API key dependency'sinden **muaf** (admin panel iç işlemleri).

| Method | Path | Yetki | Açıklama |
|---|---|---|---|
| `GET /api/users` | admin | Kullanıcı listesi (şifre hariç) |
| `POST /api/users` | admin | Yeni kullanıcı ekle |
| `DELETE /api/users/{username}` | admin | Kullanıcı sil |
| `PUT /api/users/{username}/password` | admin (başkası) / any (kendi) | Şifre değiştir |

**Silme kuralı:** Son admin silinemez. Kullanıcı kendi hesabını silemez.

**`POST /api/users` gövdesi:**
```json
{
  "username": "operator1",
  "password": "güçlüŞifre",
  "role": "viewer"
}
```

**`PUT /api/users/{username}/password` gövdesi:**
```json
{
  "current_password": "eskiŞifre",   // kendi şifresiyse zorunlu
  "new_password": "yeniŞifre"
}
```

### Admin Panel Bölümü (`#users`)

Sidebar'a `Kullanıcılar` linki eklenir.

**Bölüm içeriği:**
- Kullanıcı tablosu: username, rol badge, sil butonu (son admin'de disabled)
- "Kullanıcı Ekle" formu: username + şifre + rol dropdown
- "Şifremi Değiştir" formu: mevcut şifre + yeni şifre + onayla

**viewer rolü için:** Kullanıcılar bölümü sidebar'da görünmez. Kaydet butonları ve form alanları disabled.

---

## Dosya Değişiklik Özeti

| Dosya | Değişiklik |
|---|---|
| `app/auth.py` | **Yeni** — `verify_api_key`, `get_current_user`, `require_admin` |
| `app/db.py` | `users` tablosu SCHEMA'ya eklenir |
| `app/main.py` | Hardcoded credentials kaldırılır, migrasyon kodu eklenir, kullanıcı endpoint'leri eklenir, apikey/generate endpoint'i eklenir |
| `app/config.py` | `api_key` DEFAULTS'a eklenir (boş string) |
| `app/routers/api.py` | Router'a `Depends(verify_api_key)`, yeni `GET /api/device` endpoint'i |
| `app/routers/admin.py` | Router'a `Depends(verify_api_key)` |
| `app/templates/admin.html` | "API Erişimi" + "Kullanıcılar" bölümleri, sidebar linkleri |
| `app/static/js/admin.js` | API key UI + kullanıcı yönetimi UI |
