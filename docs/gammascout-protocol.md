# GammaScout Communication Interface Protocol

Kaynak: [Gamma-Scout Communication Interface Protocol V1.12](https://www.gamma-scout.com/wp-content/uploads/2024/11/Gamma-Scout_Communication-Interface-Protocol_V.-1.12.pdf)

## Cihaz Bilgileri (Bu Cihaz)

| Alan | Değer |
|------|-------|
| Firmware | 7.14Lb07 |
| Seri No | 085875 |
| Bağlantı | USB FTDI, /dev/ttyUSB0 |
| Baud Rate | 460800 |
| Seri Ayarlar | 7 data bits, Even parity, 1 stop bit (7,E,1) |

## Seri Port Ayarları (Firmware'e göre)

| Firmware | Baud Rate | Format |
|----------|-----------|--------|
| < 6.00 | 2400 | 7,E,1 |
| 6.00 - 6.89 | 9600 | 7,E,1 |
| >= 6.90 | 460800 | 7,E,1 |

## Protokol Genel Yapısı

- Host, cihaza tek bir komut karakteri gönderir.
- Bazı komutlar ek parametre bloğu bekler.
- Tüm veri okunabilir ASCII (CR ve LF hariç).
- Komut gönderildikten sonra sonraki karakter için **en az 550 ms** beklenmeli.
- Parametre bloğundaki ardışık karakterler arasında 1-2 ms gecikme önerilir.
- Cihaz echo yapmaz.

## Modlar ve Komutlar

### Standard Mod (varsayılan)

| Komut | Açıklama |
|-------|----------|
| `v` | Mevcut modu döndürür ("Standard") |
| `P` | PC moduna geçiş |
| `O` | Classic online moda geçiş (sadece online cihazlar) |
| `R` | Dose rate online moda geçiş (sadece online cihazlar) |
| `D` | Dose online moda geçiş (sadece online cihazlar) |

### PC Modu (FW >= 6.90)

| Komut | Açıklama |
|-------|----------|
| `v` | FW version, CPU version (6.90), SN, kullanılan bellek, tarih ve saat |
| `c` | Internal conversion data dump |
| `z` | Protokol pointer'ını bellek başına sıfırlar |
| `t` | Tarih/saat ayarı (format: "DDMMYYhhmmss") |
| `b` | Protokol belleğini dump eder |
| `N` | Warmstart (FW >= 6.90) |
| `X` | PC modundan çıkış |
| `h` | Internal h-data (FW >= 7.04) |
| `s` | Internal s-data (FW >= 7.04) |

> **DİKKAT:** `i` komutu cold start yapar ve cihazı sıfırlar! FW >= 6.90'da kaldırılmıştır.

### Online Modlar (sadece online cihazlar)

| Komut | Açıklama |
|-------|----------|
| `v` | Mevcut modu döndürür ("Online x") |
| `P` | PC moduna geçiş |
| `X` | Online moddan çıkış |
| `s` | Online durum ve pulse'ları iste (Classic online) |
| `0`-`9` | Online interval ayarla (Classic online) |

## Protokol Bellek Dump Formatı (FW >= 6.00)

```
f5ef5915120114f500f5ee05000013f5ef5915120114f505f5eec0000290f50a10
00130018001d0014001800240024001100160017001100170013001e001f001587
```

- Adres veya boşluk yok.
- Her satır 33 byte: ilk 32 byte protokol verisi, son byte mod256 checksum.
- Veri, 2 byte'lık pulse girişleri veya özel kodlardan (special codes) oluşur.

## Pulse Girişi Decode

2 byte'lık pulse girişi: üst 5 bit exponent, alt 11 bit mantissa.

```
pulse_count = 2^exponent * mantissa
```

Örnek: `0x3E27` = `%0011_1110_0010_0111`
- Exponent: 7 (üst 5 bit: `00111`)
- Mantissa: 1575 (alt 11 bit: `11000100111`)
- Sonuç: 2^7 * 1575 = 201600

Yüksek nibble `0xF` ise → özel kod (pulse girişi değil).

## Özel Kodlar (FW 7.01 - 7.09)

| Kod | Açıklama |
|-----|----------|
| `0xF5` | Genel özel kod, ardından event byte gelir |
| `0xF8` | Internal özel byte, ardından size byte + atlanacak veri |
| `0xF9` | Dose rate overflow (> 1000 µSv/h) |
| `0xFA` | Dose alarm tetiklendi |
| `0xFB` | Dose alarm + Dose rate overflow |
| `0xFC` | Dose rate alarm tetiklendi |
| `0xFD` | Dose rate alarm + Dose rate overflow |
| `0xFE` | Dose rate alarm + Dose alarm |
| `0xFF` | Dose rate alarm + Dose alarm + Dose rate overflow |

### 0xF5 Event Byte'ları (FW >= 7.01)

| Event Byte | Açıklama |
|------------|----------|
| `0x00` | Protokol devre dışı |
| `0x01` | Interval: 1 hafta |
| `0x02` | Interval: 3 gün |
| `0x03` | Interval: 1 gün |
| `0x04` | Interval: 12 saat |
| `0x05` | Interval: 2 saat |
| `0x06` | Interval: 1 saat |
| `0x07` | Interval: 30 dakika |
| `0x08` | Interval: 10 dakika |
| `0x09` | Interval: 5 dakika |
| `0x0A` | Interval: 2 dakika |
| `0x0B` | Interval: 1 dakika |
| `0x0C` | Interval: 30 saniye |
| `0x0D` | Interval: 10 saniye |
| `0xEA` | Cs137 conversion aktif (FW >= 7.10) |
| `0xEB` | Co60 conversion aktif (FW >= 7.10) |
| `0xED` | Timestamp, 6 byte: ssmmhhDDMMYY |
| `0xEE` | Out-of-band protocol interval |
| `0xEF` | Timestamp, 5 byte: mmhhDDMMYY |
| `0xF0-0xFE` | Debug flag'leri (yok sayılmalı) |

## Önerilen Okuma Sırası

1. `P` → PC moduna gir
2. `v` → Firmware ve cihaz bilgilerini al
3. `h` → Internal h-data (FW >= 7.04)
4. `s` → Internal s-data (FW >= 7.04)
5. `c` → Conversion data
6. `b` → Protokol bellek dump
7. `X` → PC modundan çık