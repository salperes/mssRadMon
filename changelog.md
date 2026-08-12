---------------------------------------------------------
Rev. ID    : 2
Version    : 1.4.3
Rev. Date  : 12.08.2026
Rev. Time  : 15:59:50
Rev. Prompt: Röleler çekmiyor (radmon02); 192.168.152.73 makinesinde çalışıyor — iki makine karşılaştırılarak kök neden bulunup düzeltilecek.

Rev. Report: (
- Kök neden: RelayBoard yalnızca lifespan'de bir kez kuruluyordu. radmon02'de servis 15:17'de eski pinlerle (BCM17/27/22) açıldı, 15:44'te PUT /api/settings ile pinler 26/20/21 yapıldı ama röle kartı yeniden kurulmadı → API 200 dönüyor, röle çekmiyor. radmon73 aynı kodda; DB'si zaten doğruyken başladığı için sorun görünmüyordu (pin değişiminde aynı hatayı verirdi).
- app/config.py: gpio_buzzer_pin/gpio_light_pin/gpio_emergency_pin varsayılanları 17/27/22 → 26/20/21 (Waveshare CH1/CH2/CH3). Eski varsayılanlar DB'ye seed edildiği için main.py'deki `or "26"` fallback'i hiç devreye girmiyordu; yeni kurulan her cihaz yanlış pinle açılıyordu. Mevcut DB'ler etkilenmez (Config.init üzerine yazmaz)
- app/relay.py: DEFAULT_PINS ve GPIO_PIN_KEYS sabitleri; resolve_channels(config) — pin çözümü tek yerde, geçersiz/boş değerde varsayılana düşer (önce int() ValueError ile lifespan'i çökertebiliyordu); RelayBoard._open() ayrıştırıldı; pins() canlı sürülen pinleri döndürür; reconfigure() pinleri kapatıp yeniden açar, değişiklik yoksa no-op, çekili kanalları yeni pinler üzerinde geri çeker (aktif alarmda çıkış düşmez); close() artık _pins'i de temizler
- app/main.py: relay_channels bloğu resolve_channels(config) çağrısıyla değiştirildi
- app/routers/admin.py: update_settings gpio_* anahtarı değiştiyse relay.reconfigure çağırıyor, yanıta relay_reloaded eklendi; yeni GET /api/relay/pins — kanal başına canlı/yapılandırılmış pin ve ok karşılaştırması
- app/templates/admin.html: "Pin değişikliği servis yeniden başlatılınca etkin olur" notu güncellendi; relayPinStatus göstergesi eklendi
- app/static/js/admin.js: refreshRelayPins() — aktif pinleri gösterir, pin açılamazsa (BUSY vb.) kırmızı uyarı; açılışta ve gpio_* içeren kayıt sonrası tazelenir
- tests/test_relay.py: yeni — 9 test (varsayılan pinler, DB override, bozuk değerde fallback, pins(), reconfigure no-op/değişim/aktif çıkış koruma, update_settings hot-reload ve gpio dışı ayarda dokunmama). Gerçek GPIO'ya dokunmamak için FakeOutputDevice ile monkeypatch
- Doğrulama: servis restart sonrası journal "Röle kanalı 'buzzer' → BCM26 / 'light' → BCM20 / 'emergency' → BCM21"; pin doluluk testi 26/20/21 BUSY, 17/27/22 FREE; pytest 163 passed (öncesi 154), 11 failure baseline ile birebir aynı (test_msg_service/test_auth/test_serial_reader — bu değişiklikle ilgisiz)
- Not: changelog'da 1.4.1 ve 1.4.2 kayıtları atlanmış; bu kayıt 1.4.3 olarak devam ediyor
)
---------------------------------------------------------
---------------------------------------------------------
Rev. ID    : 1
Version    : 1.4.0
Rev. Date  : 26.05.2026
Rev. Time  : 13:49:52
Rev. Prompt: Waveshare 3-kanal röle kartı entegrasyonu; alarm çıkışlarının röle üzerinden sürülmesi; admin paneline manuel röle test arayüzü; version bump + commit/push.

Rev. Report: (
- app/relay.py: yeni modül — RelayBoard (3 kanal, active-low, gpiozero OutputDevice(active_high=False, initial_value=False)); isimli kanal API'si (set/has/is_on/all_off/close); GPIO yoksa mock fallback
- app/alarm.py: AlarmManager artık constructor'da RelayBoard alıyor; doğrudan OutputDevice ve _gpio_devices kaldırıldı; alarm aksiyonları (buzzer/light/emergency) relay.set üzerinden çekiliyor; buzzer pattern (1s on / 5s off) relay üzerinden; silence/clear akışı relay.all_off ile
- app/main.py: lifespan'de pin haritası config'den okunup RelayBoard yaratılıyor (varsayılan CH1=26, CH2=20, CH3=21); AlarmManager'a relay parametresi geçildi; app.state.relay eklendi; shutdown'da relay.close()
- app/routers/admin.py: GET /api/relay/state ve POST /api/relay/test endpoint'leri; aktif alarm varken manuel müdahale 409 ile reddedilir; geçersiz kanal 400; yapılandırılmamış kanal 404
- app/templates/admin.html: Alarm & GPIO sekmesinde "Röle Manuel Test" kartı (3 kanal × toggle butonu + durum noktası); GPIO pin kartına Waveshare not satırı eklendi
- app/static/js/admin.js: toggle handler (single button: Çek/Bırak), açılışta GET /api/relay/state ile state senkronu; ON=accent renk + #fff text, OFF=surface + text rengi düzeltildi
- tests/test_alarm.py: OutputDevice patch'i kaldırıldı, RelayBoard MagicMock'a uyarlandı; threshold_*_duration mock'ları 0 ile eklendi; iki çağrılı _trigger helper'ı (state-machine ilk çağrıda sayacı başlatıyor); yeni test_relay_set_on_trigger
- requirements.txt: httpx ve python-multipart eklemeleri (local deploy)
- systemd/mssradmon.service: User/path alper → mssadmin (local deploy)
- db: gpio_buzzer_pin=26, gpio_light_pin=20, gpio_emergency_pin=21 olarak güncellendi (Waveshare CH1/CH2/CH3)
- venv: sistem python3-lgpio paketi venv site-packages'a symlink ile bağlandı (gpiozero artık LGPIOFactory kullanıyor)
)
---------------------------------------------------------
