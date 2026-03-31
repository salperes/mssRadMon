# mssRadMon

GammaScout Online USB radyasyon ölçer için Raspberry Pi tabanlı izleme sistemi.

## Özellikler

- Anlık doz hızı ve kümülatif doz takibi
- Canlı web dashboard (WebSocket + REST API)
- İki seviyeli alarm sistemi (High / High-High)
- GPIO çıkışları: buzzer, ışık, acil kapatma
- E-posta bildirimleri (SMTP)
- Uzak sunucuya log iletimi (HTTP POST, persistent queue)
- Yapılandırılabilir ayarlar (web admin paneli)

## Kurulum

```bash
cd /home/alper/mssRadMon
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Çalıştırma

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Tarayıcıda: `http://<rpi-ip>:8080`

## systemd ile Servis Olarak Kurma

```bash
sudo cp systemd/mssradmon.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mssradmon
sudo systemctl start mssradmon
```

## Geliştirme

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

## API

| Endpoint | Açıklama |
|----------|----------|
| `GET /api/current` | Son ölçüm |
| `GET /api/readings?last=1h` | Zaman aralığına göre okumalar |
| `GET /api/daily-dose` | Günlük kümülatif doz |
| `GET /api/status` | Cihaz durumu |
| `GET /api/alarms?last=24h` | Alarm geçmişi |
| `GET /api/settings` | Tüm ayarlar |
| `PUT /api/settings` | Ayar güncelleme |
| `WS /ws/live` | Canlı veri akışı |

## Donanım

- Raspberry Pi 5
- GammaScout Online (USB)
- GPIO 17: Buzzer
- GPIO 27: Uyarı ışığı
- GPIO 22: Acil kapatma rölesi
