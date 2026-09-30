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

## 5. Manager'a Otomatik Kayıt (auto-register)

Cihaz, açılışta ve sonra 5 dakikada bir seri numarası ve güncel IP adresiyle
radMonManager'a kayıt isteği gönderir. Manager cihazı seri numarasından bulur;
IP değiştiyse kaydı günceller ve yeni adrese kendiliğinden bağlanır.

Kayıt için gereken token, repo public olduğu için kodda **tutulmaz**; her
kurulumda `/etc/default/mssradmon` dosyasına bir kez yazılmalıdır. Bu dosya
yoksa cihaz çalışır ama **sessizce kayıt olmaz** (IP değişikliği algılanmaz).

**a) Token dosyasını oluştur** — ya şablondan:

```bash
sudo cp systemd/mssradmon.env.example /etc/default/mssradmon
sudo nano /etc/default/mssradmon      # MSSRADMON_REGISTER_TOKEN değerini gir
sudo chmod 600 /etc/default/mssradmon
```

Token, manager'daki `system_settings` tablosunun `register_token` değeriyle
**birebir aynı** olmalıdır.

ya da çalışan başka bir cihazdan, içeriği ekrana basmadan kopyalayarak
(`<kaynak>` = token'ı olan cihaz, `<yeni>` = kurulan cihaz):

```bash
# Yönetici bilgisayarından: dosyayı yeni cihazın ev dizinine taşı (sudo gerekmez)
ssh mssadmin@<kaynak> "cat /etc/default/mssradmon" | ssh mssadmin@<yeni> "umask 077; cat > ~/mssradmon.env"

# Yeni cihazda: yerine koy, geçici kopyayı sil
sudo install -m 600 ~/mssradmon.env /etc/default/mssradmon && rm ~/mssradmon.env
```

**b) Servis dosyasının token'ı okuduğunu doğrula ve yeniden başlat:**

```bash
systemctl cat mssradmon | grep EnvironmentFile   # boşsa: 4. adımdaki cp'yi tekrarla
sudo systemctl restart mssradmon
```

> Eski kurulumlarda `/etc/systemd/system/mssradmon.service` dosyasında
> `EnvironmentFile=-/etc/default/mssradmon` satırı olmayabilir. Bu durumda
> token dosyası dursa bile okunmaz; 4. adımdaki `cp` + `daemon-reload` ile
> güncel servis dosyasını kur.

**c) Kaydı kontrol et:**

```bash
journalctl -u mssradmon --since "-5min" | grep -i regist
# Beklenen: "Registered with manager: <device-id> (status=created|updated)"
```

Notlar:

- Kayıt, seri numarası GammaScout'tan okunana kadar **ertelenir** (boş seri ile
  mükerrer cihaz oluşmasın diye). GammaScout takılı değilse kayıt olmaz.
- Aynı GammaScout başka bir Pi'ye takılırsa manager mevcut kaydı günceller;
  yeni cihaz oluşturmaz.
- Cihaz NAT / SSH tüneli arkasındaysa auto-register **açma**: cihaz kendi yerel
  IP'sini bildirir ve manager'daki tünel adresinin üzerine yazar.
- Manager farklı bir adresteyse dosyadaki `MSSRADMON_MANAGER_URL` satırını aç.

## 6. Erişim

Tarayıcıdan `http://<pi-ip>:8090` adresine gidin.

- Dashboard: `/`
- Admin paneli: `/admin`
