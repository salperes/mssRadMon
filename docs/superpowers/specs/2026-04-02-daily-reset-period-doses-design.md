# Tasarım: Günlük Doz Sıfırlama (UTC+3) ve Periyodik Doz Gösterimi

**Tarih:** 2026-04-02  
**Konu:** Günlük kümülatif dozun gece 00:00 (Türkiye yerel saati, UTC+3) itibarıyla sıfırlanması; aylık, 3 aylık, 6 aylık ve yıllık dozların dashboard'da gösterilmesi

---

## Problem

- Mevcut `/api/daily-dose` endpoint'i günlük başlangıcı UTC 00:00 olarak hesaplıyor. Türkiye'de bu 03:00'a denk geldiğinden günlük doz yanlış sıfırlanıyor.
- Dashboard'da yalnızca günlük kümülatif doz gösteriliyor; uzun dönem doz bilgisi yok.

---

## Çözüm

### 1. UTC+3 Düzeltmesi

`app/routers/api.py` dosyasında:

```python
TZ_TR = timezone(timedelta(hours=3))
```

`get_daily_dose()` fonksiyonunda gün başlangıcı:

```python
now_local = datetime.now(TZ_TR)
today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat()
```

Bu değişiklik mevcut `/api/daily-dose` endpoint'inin davranışını da düzeltir.

### 2. Yeni Endpoint: `GET /api/period-doses`

`readings` tablosundaki `cumulative_dose` farkından her periyot için doz hesaplanır:

```
doz = son_cumulative_dose - ilk_cumulative_dose (periyot başından itibaren)
```

**Periyot başlangıç noktaları (UTC+3 yerel saat):**

| Periyot   | Başlangıç           |
|-----------|---------------------|
| Günlük    | Bugün 00:00         |
| Aylık     | Bu ayın 1'i 00:00   |
| 3 Aylık   | Çeyrek başı (Oca/Nis/Tem/Eki 1) 00:00 |
| 6 Aylık   | Oca 1 veya Tem 1 00:00 |
| Yıllık    | Oca 1 00:00         |

**Yanıt formatı:**

```json
{
  "daily": 1.23,
  "monthly": 45.60,
  "quarterly": 120.30,
  "half_yearly": 230.10,
  "yearly": 450.20
}
```

Her periyot için iki sorgu atılır (ilk ve son cumulative_dose), fark döndürülür. Veri yoksa 0.0 döner.

### 3. Frontend Değişiklikleri

**`dashboard.html`** — "Günlük Kümülatif Doz" kartına periyot satırları eklenir:

```
┌─────────────────────────────┐
│ Günlük Kümülatif Doz        │
│                             │
│    [büyük]  1.23 µSv        │  ← mevcut (id="dailyDose")
│                             │
│  Aylık:      45.60 µSv      │  ← küçük font (id="monthlyDose")
│  3 Aylık:   120.30 µSv      │  ← (id="quarterlyDose")
│  6 Aylık:   230.10 µSv      │  ← (id="halfYearlyDose")
│  Yıllık:    450.20 µSv      │  ← (id="yearlyDose")
└─────────────────────────────┘
```

**`static/css/style.css`** — İki yeni sınıf:
- `.period-doses` — üstte ince ayraç, küçük padding
- `.period-dose-row` — `font-size: 0.8rem`, muted renk, sayılar sağa hizalı

**`static/js/dashboard.js`** — Sayfa yüklenince ve her 60 saniyede `/api/period-doses` fetch edilir, 5 span güncellenir.

---

## Etkilenen Dosyalar

| Dosya | Değişiklik |
|-------|------------|
| `app/routers/api.py` | UTC+3 sabiti, `get_daily_dose()` düzeltmesi, yeni endpoint |
| `app/templates/dashboard.html` | Periyot satırları HTML |
| `app/static/css/style.css` | `.period-doses`, `.period-dose-row` sınıfları |
| `app/static/js/dashboard.js` | `/api/period-doses` fetch + DOM güncellemesi |

---

## Kapsam Dışı

- Periyot verilerinin ayrı tabloda saklanması (gerek yok; `readings` tablosu yeterli)
- Timezone admin panelinden konfigüre edilmesi (UTC+3 sabit)
- Geçmiş periyot karşılaştırması veya grafik gösterimi
