# mssRadMon Kurulum Rehberi

GammaScout radyasyon monitörü web arayüzü kurulumu.

## Gereksinimler

- Raspberry Pi (Raspberry Pi OS)
- Python 3.11+
- GammaScout cihazı (USB-Serial / FTDI)

## 1. Arşivi Aktar ve Aç

```bash
# Arşivi yeni Pi'ye kopyala (kaynak Pi'den)
scp /home/alper/mssRadMon.tgz alper@<yeni-pi-ip>:/home/alper/

# Yeni Pi'de aç
cd /home/alper
tar xzf mssRadMon.tgz
```

## 2. Python Sanal Ortamı ve Bağımlılıklar

```bash
cd /home/alper/mssRadMon
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Seri Port İzni

Kullanıcının seri porta erişebilmesi için `dialout` grubuna eklenmesi gerekir:

```bash
sudo usermod -aG dialout alper
```

Değişikliğin geçerli olması için oturumu kapatıp açın veya yeniden başlatın.

## 4. Systemd Servisi

```bash
sudo cp systemd/mssradmon.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mssradmon
```

Servis durumunu kontrol etmek için:

```bash
sudo systemctl status mssradmon
journalctl -u mssradmon -f
```

## 5. Erişim

Tarayıcıdan `http://<pi-ip>:8090` adresine gidin.

- Dashboard: `/`
- Admin paneli: `/admin`
