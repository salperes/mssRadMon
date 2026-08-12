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
