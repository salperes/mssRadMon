# Admin Sayfa Kimlik Doğrulama — Tasarım Dokümanı

**Tarih:** 2026-04-02  
**Kapsam:** `/admin` sayfası için session cookie tabanlı giriş koruması

---

## Gereksinimler

- `/admin` sayfasına giriş yapmadan erişilemesin
- Kullanıcı adı: `mssadmin`, Şifre: `Ankara12!`
- API endpoint'leri (`/api/*`) korunmayacak — yalnızca HTML admin sayfası
- Logout butonu olsun
- Session 8 saat geçerli

---

## Mimari

### Yeni Route'lar (`app/main.py`)

| Route | Method | Açıklama |
|-------|--------|----------|
| `/admin/login` | GET | Login formu göster |
| `/admin/login` | POST | Credentials doğrula, cookie set et, `/admin`'e redirect |
| `/admin/logout` | POST | Cookie sil, `/admin/login`'e redirect |
| `/admin` | GET | Cookie yoksa `/admin/login`'e redirect (mevcut route güncellenir) |

### Session Mekanizması

- Kütüphane: `itsdangerous.URLSafeTimedSerializer`
- Cookie adı: `mssradmon_session`
- İmzalama: `SECRET_KEY` sabit string (main.py içinde)
- TTL: 8 saat (`max_age=28800`)
- Cookie: `httponly=True`, `samesite="lax"`

### Credentials

`main.py` içinde sabit:

```python
ADMIN_USERNAME = "mssadmin"
ADMIN_PASSWORD = "Ankara12!"
```

### Yardımcı Fonksiyonlar (`main.py`)

```python
def _make_session_cookie(response, username): ...   # cookie yaz
def _get_session(request) -> str | None: ...        # cookie oku, doğrula
```

---

## Yeni Dosyalar

### `app/templates/login.html`

- `base.html`'i extend etmez (navbar yok)
- Sade form: kullanıcı adı + şifre + Giriş butonu
- Hatalı girişte kırmızı hata mesajı
- Mevcut style.css'i kullanır

---

## Değişen Dosyalar

| Dosya | Değişiklik |
|-------|------------|
| `app/main.py` | `itsdangerous` import, sabit credentials, `_make_session_cookie`, `_get_session`, `/admin/login` GET/POST, `/admin/logout` POST, `/admin` GET güncellenir |
| `app/templates/admin.html` | Navbar'a Logout butonu eklenir |

---

## Bağımlılık

`itsdangerous` FastAPI/Starlette ile zaten yüklü gelir. Ek paket gerekmez.

---

## Hata Durumları

| Durum | Davranış |
|-------|----------|
| Cookie yok / geçersiz | `/admin/login`'e redirect |
| Cookie süresi dolmuş (8s+) | `/admin/login`'e redirect |
| Yanlış credentials | Login sayfası, `?error=1` ile hata mesajı |
| Başarılı giriş | `/admin`'e redirect |
