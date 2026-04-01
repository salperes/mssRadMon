# Versiyonlama ve Changelog Kuralları

Bu dosya, mssRadMon projesinde uygulanacak versiyonlama ve changelog standartlarını tanımlar.

Version bilgisi dashboard ve admin sayfalarının footer alanında gösterilir.
Her kod değişikliğinde commit yapılır; push ancak kullanıcı talebi ile olur.
Git repo: https://github.com/salperes/mssRadMon (mevcut değilse kullanıcıdan oluşturması talep edilir)

---

## Versiyon Formatı

**MAJOR.MINOR.Version**

| Parça   | Açıklama                                                   | Örnek |
|---------|------------------------------------------------------------|-------|
| MAJOR   | Ana sürüm (büyük mimari değişiklikler)                     | 1     |
| MINOR   | Alt sürüm (yeni özellik/modül eklemeleri)                  | 1     |
| Version | Sürüm sayacı — MINOR bump'ta 0'dan başlar, her kod değişikliğinde 1 artar | 3 |

Örnek: `1.1.3`

**Rev. ID ≠ Version:** Rev. ID, CHANGELOG'daki sürekli artan kimlik numarasıdır (200, 201…). Version ise MINOR'a bağlı ayrı bir sayaçtır (1, 2, 3…). Her CHANGELOG kaydında ikisi birlikte yer alır.

---

## Versiyon Güncellenecek Dosyalar

Her versiyon artışında şu dosyalar güncellenir:

| Dosya                  | Alan / Açıklama                        |
|------------------------|----------------------------------------|
| `app/__version__.py`   | `__version__ = "X.Y.Z"` satırı        |
| `CLAUDE.md`            | Mevcut Versiyon satırı                 |

---

## Changelog Formatı

Dosya: `changelog.md` (proje root'unda)

Her değişiklik kaydı şu formatta **en üste (prepend)** eklenir:

```
---------------------------------------------------------
Rev. ID    : {COUNTER}
Version    : {MAJOR}.{MINOR}.{Version}
Rev. Date  : DD.MM.YYYY
Rev. Time  : HH:MM:SS
Rev. Prompt: {Kullanıcının verdiği prompt/istek özeti}

Rev. Report: (
{Yapılan değişikliklerin madde madde özet raporu}
- app/: ...
- templates/: ...
- static/js/: ...
- db/: ...
)
---------------------------------------------------------
```

### Kurallar

1. **Newest first (prepend):** Yeni kayıt dosyanın **en üstüne** eklenir, en yeni kayıt her zaman en üstte
2. **Lokal saat:** Rev. Time lokal zaman dilimini kullanır
3. **Rev. ID:** Önceki kaydın ID'si + 1 (sıralı, boşluksuz, sürekli artar)
4. **Version:** Önceki `Version` üçüncü basamağı + 1; MINOR bump'ta `0` → `1`'den başlar
5. **Dosya yoksa:** Yeni `changelog.md` oluştur, Rev. ID = 1'den başla
6. **Mevcut kayıtlar değiştirilmez**

### Arşivleme

- `changelog.md` en fazla **11 kayıt** tutar
- 11'i aşınca en eski 10 kayıt arşivlenir: `archives/changelog_{START}-{END}.md`
  - Örnek: `archives/changelog_001-010.md`, `archives/changelog_011-020.md`
- Arşiv dosyalarında da **newest first** sıralama
- Kalan kayıtlar (en yeniler) `changelog.md`'de kalır

---

## Kod Değişikliği Sonrası Standart Akış (ZORUNLU)

Her kod değişikliğinden sonra bu sıra **eksiksiz** takip edilir:

```
1. TEST             → pytest çalıştır (source .venv/bin/activate && pytest)
2. changelog.md     → Changelog kaydı ekle — en üste (Rev. ID, Version, Date, Time, Prompt, Report)
3. Version bump     → app/__version__.py güncelle
4. CLAUDE.md        → Versiyon numarasını güncelle (gerekirse yeni özellik dokümanı ekle)
5. Commit           → Değişiklikleri commit et (push sadece kullanıcı talebiyle)
6. Deploy           → sudo systemctl restart mssradmon (kullanıcı isterse)
7. Verify           → Health endpoint'ten versiyon doğrula
8. Memory güncelle  → MEMORY.md "Current Version" ve "Current Version Counter" alanlarını güncelle
```

**KRİTİK:**
- Test adımı atlanmaz.
- Deploy'u bu adımlar OLMADAN yapma: önce test + changelog/versiyon + commit, sonra deploy.

---

## Health Endpoint ile Doğrulama

Deploy sonrası versiyon kontrolü:

```bash
curl -s http://localhost:8090/api/health
# Beklenen: {"status":"ok","version":"1.0.1",...}
```

Health endpoint (`/api/health`) `app/__version__.py`'deki `__version__` değerini döner.

---

## Deploy Komutu

```bash
sudo systemctl restart mssradmon
# Durum kontrolü:
sudo systemctl status mssradmon
# Log takibi:
sudo journalctl -u mssradmon -f
```

---

## Örnek Akış

Kullanıcı: "USB replug'da otomatik yeniden bağlan"

```
1. Kod değişikliklerini yap (app/serial_reader.py)
2. pytest çalıştır
3. changelog.md'nin en üstüne ekle:
   ---------------------------------------------------------
   Rev. ID    : 2
   Version    : 1.0.2
   Rev. Date  : 01.04.2026
   Rev. Time  : 16:25:00
   Rev. Prompt: USB replug'da otomatik yeniden bağlan

   Rev. Report: (
   - app/serial_reader.py: disconnect() içinde _device_info sıfırlandı,
     run() döngüsüne ardışık hata sayacı eklendi
   - /etc/udev/rules.d/99-gammascout.rules: FTDI SN'e göre sabit sembolik
     link (/dev/ttyGammaScout) oluşturuldu
   )
   ---------------------------------------------------------

4. app/__version__.py: __version__ = "1.0.2"
5. CLAUDE.md: Mevcut Versiyon satırını güncelle
6. Commit (push sadece kullanıcı talebiyle)
7. sudo systemctl restart mssradmon + curl /api/health doğrula
```
