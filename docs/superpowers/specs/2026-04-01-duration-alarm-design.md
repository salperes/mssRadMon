# Sureli Alarm Esikleri Tasarim Dokumani

## Ozet

Alarm esikleri anlik degil, belirli bir sure boyunca kesintisiz asildiginda tetiklenir. Ornegin high esigi 120 sn boyunca asilirsa alarm olusur. Sure dolmadan esik altina dusulurse sayac sifirlanir. Sure boyunca dashboard'da on uyari (pending alarm) gosterilir.

## Config Degisiklikleri

DEFAULTS'a iki yeni ayar:
- `threshold_high_duration`: "120" (saniye)
- `threshold_high_high_duration`: "15" (saniye)

Bu ayarlar admin panelde Alarm & GPIO bolumunde esik degerlerinin yaninda gorunur.

## AlarmManager Degisiklikleri

### Yeni State Alanlari

- `_exceed_start: float | None` — threshold asiminin basladigi monotonic zaman
- `_exceed_level: AlarmLevel | None` — hangi seviyede asim sayiliyor

### check() Mantigi

1. Doz hizi threshold altindaysa:
   - Sayac sifirla (`_exceed_start = None`, `_exceed_level = None`)
   - Mevcut alarm varsa kapat (`_clear_alarm`)
   - return `None`

2. Doz hizi threshold ustundeyse:
   - Seviyeyi belirle (high/high_high)
   - Seviye degistiyse: sayaci sifirla, yeni seviyeden basla
   - Seviye ayni: gecen sureyi hesapla
     - Sure dolmussa: `_trigger_alarm()` cagir
     - Sure dolmamissa: pending durumda kal

3. Zaten tetiklenmis alarm varsa ve ayni seviyedeyse: tekrar tetikleme

### get_pending() Metodu (yeni)

Dashboard ve WS icin pending alarm bilgisi dondurur:

```python
{
    "alarm_pending": True/False,
    "alarm_pending_level": "high" | "high_high" | None,
    "alarm_pending_elapsed": 45,     # gecen sure (sn)
    "alarm_pending_duration": 120,   # toplam gereken sure (sn)
}
```

## WebSocket ve API

### WS Mesaji

on_reading callback'indeki WS mesajina pending alarm bilgisi eklenir. `alarm_manager.get_pending()` cagrilir ve sonuc msg dict'e merge edilir.

### /api/current Endpoint

Mevcut response'a pending alarm alanlari eklenir.

## Dashboard Frontend

Mevcut alarm banner'i pending durumda da gosterilir:
- Sari (high) veya kirmizi (high_high) arka plan
- Metin: "HIGH esigi asildi — 45/120 sn" veya "KRITIK esik asildi — 8/15 sn"
- WS mesajiyla gercek zamanli guncellenir
- Sure dolup alarm tetiklendiginde mevcut alarm banner davranisi devam eder

## Admin Panel

Alarm & GPIO bolumunde esik degerlerinin yanina sure inputlari eklenir:

```
[High Esigi (uSv/h)]    [High Suresi (sn)]
[High-High Esigi]        [High-High Suresi]
```

Input ID'leri: `threshold_high_duration`, `threshold_high_high_duration`
Mevcut FIELDS listesine eklenir, saveSettings ile kaydedilir.

## Etkilenen Dosyalar

| Dosya | Degisiklik |
|-------|-----------|
| `app/config.py` | DEFAULTS'a 2 yeni key |
| `app/alarm.py` | check() sure mantigi, get_pending(), yeni state alanlari |
| `app/main.py` | WS mesajina pending bilgisi |
| `app/routers/api.py` | /api/current response'una pending bilgisi |
| `app/static/js/dashboard.js` | Banner'da on uyari gosterimi |
| `app/templates/admin.html` | Sure input alanlari |
| `app/static/js/admin.js` | FIELDS listesine yeni keyler |
