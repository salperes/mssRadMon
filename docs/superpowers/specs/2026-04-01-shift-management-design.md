# Vardiya Yonetimi Tasarim Dokumani

## Ozet

Uygulamaya esnek vardiya tanimlama ve vardiya bazli kumulatif doz takibi ozelligi eklenir. Kullanici admin panelden istedigi kadar vardiya ekleyip cikarabilir (isim + saat araligi + hafta gunleri). Dashboard'da aktif vardiyanin anlik dozu ve gecmis vardiya dozlari gosterilir.

## Veri Modeli

### Vardiya Tanimlari (settings tablosu, JSON)

`shifts` key'inde JSON array olarak saklanir:

```json
[
  {
    "id": "s1",
    "name": "Vardiya 1",
    "start": "08:00",
    "end": "16:00",
    "days": [1, 2, 3, 4, 5]
  }
]
```

- `days`: ISO weekday (1=Pazartesi, 7=Pazar)
- `id`: Otomatik uretilen kisa ID. Vardiya silinip eklendiginde gecmis kayitlar bozulmaz.

### Vardiya Doz Gecmisi (yeni tablo: shift_doses)

```sql
CREATE TABLE IF NOT EXISTS shift_doses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id TEXT NOT NULL,
    shift_name TEXT NOT NULL,
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    dose REAL NOT NULL DEFAULT 0.0,
    completed INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_shift_doses_date ON shift_doses(date);
```

- `completed=0`: vardiya devam ediyor
- `completed=1`: vardiya bitti, doz dondu
- `shift_name` denormalize saklanir — vardiya adi sonradan degisse bile gecmis kayitlar dogru kalir

## Backend Mantigi

### Yeni Dosya: app/shift.py — ShiftManager Sinifi

Metodlar:
- `check(cumulative_dose)`: Her okumada cagrilir. Aktif vardiyayi belirler, dozu gunceller.
- `get_current()`: Aktif vardiya adi + anlik vardiya dozu dondurur.
- `get_history(days)`: Son N gunun tamamlanmis vardiya dozlarini dondurur.

### Aktif Vardiya Tespiti

Her yeni okumada:
1. Su anki saat ve gun alinir (lokal saat)
2. `shifts` JSON'dan eslesen vardiya bulunur (saat araligi + gun kontrolu)
3. Gece vardiyasi destegi: `start > end` ise (orn. 22:00-06:00) gun gecisi hesaplanir

### Doz Hesaplama

Her okumada:
- Aktif vardiya varsa: `shift_doses` tablosunda bugun + bu shift_id icin kayit aranir
  - Yoksa: yeni kayit olusturulur, `dose = 0`
  - Varsa: `dose += (yeni_cumulative - onceki_cumulative)` farki ile guncellenir
- Aktif vardiya yoksa: vardiya dozu hesaplanmaz

### Vardiya Bitisi

- Yeni okuma geldiginde onceki aktif vardiya artik aktif degilse: o kaydin `completed = 1` yapilir
- Uygulama yeniden baslarsa: `completed=0` olan eski kayitlar kontrol edilip kapatilir

### Yeni API Endpoint'leri (api.py)

| Endpoint | Aciklama |
|----------|----------|
| `GET /api/shift/current` | Aktif vardiya adi + anlik vardiya dozu |
| `GET /api/shift/history?days=7` | Son N gunun tamamlanmis vardiya dozlari |

## Frontend

### Dashboard — Vardiya Dozu Karti

Mevcut iki kartin yanina ucuncu kart eklenir:

```
[ Anlik Doz Hizi ] [ Gunluk Kumulatif Doz ] [ Vardiya Dozu ]
     0.045 uSv/h         0.127 uSv              Vardiya 1
                                                 0.089 uSv
```

- Aktif vardiya yoksa kart "Vardiya disi" gosterir
- WebSocket mesajina `shift_name` ve `shift_dose` eklenir, gercek zamanli guncellenir

### Dashboard — Gecmis Vardiya Dozlari Tablosu

Kartlarin altinda tablo:

| Tarih | Vardiya | Saat | Doz (uSv) |
|-------|---------|------|-----------|
| 01.04.2026 | Vardiya 1 | 08:00-16:00 | 0.142 |
| 01.04.2026 | Vardiya 2 | 16:00-00:00 | 0.098 |

- Varsayilan son 7 gun gosterilir
- Sayfa yuklendiginde `/api/shift/history?days=7` cekilir

### Admin — Vardiyalar Bolumu

Sidebar'a "Vardiyalar" linki eklenir. Bolum icerigi:

- Mevcut vardiyalarin listesi (kart seklinde)
- Her vardiya kartinda: isim, baslangic/bitis saati, aktif gunler (checkbox grubu), sil butonu
- Altta "Vardiya Ekle" formu: isim + baslangic saati + bitis saati + gun secimi
- "Ayarlari Kaydet" butonu: tum vardiyalari JSON olarak `/api/settings` PUT ile gonderir

## Etkilenen Dosyalar

| Dosya | Degisiklik |
|-------|-----------|
| `app/shift.py` | Yeni — ShiftManager sinifi |
| `app/db.py` | SCHEMA'ya shift_doses tablosu eklenir |
| `app/config.py` | DEFAULTS'a `shifts` key eklenir (bos JSON array) |
| `app/main.py` | ShiftManager olusturulur, on_reading'e entegre edilir, WS mesajina shift verisi eklenir |
| `app/routers/api.py` | `/api/shift/current` ve `/api/shift/history` endpoint'leri |
| `app/templates/dashboard.html` | Vardiya dozu karti + gecmis tablosu |
| `app/static/js/dashboard.js` | Vardiya verisi fetch + WS guncelleme + gecmis tablosu |
| `app/templates/admin.html` | Vardiyalar bolumu (sidebar link + section) |
| `app/static/js/admin.js` | Vardiya CRUD islemleri |
