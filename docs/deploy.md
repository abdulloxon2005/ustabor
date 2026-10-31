# UstaBor — serverga joylash (deploy) qo'llanmasi

Docker Compose asosida: backend (FastAPI + SQLite), frontend (Nginx — statik fayllar +
`/api/v1` va `/media` uchun proksi). Baza va yuklangan rasmlar Docker tomlarida
(volume) saqlanadi, shuning uchun konteynerlar qayta qurilganda ma'lumot yo'qolmaydi.

## ⚠️ Productionga chiqishdan oldin: SMS hali MOCK

`backend/app/services/sms.py` hozircha **haqiqiy SMS yubormaydi** — OTP kodi faqat
server logiga va `sms_outbox.log` fayliga yoziladi. Bu degani: **hech bir haqiqiy
foydalanuvchi ro'yxatdan o'ta yoki parolni tiklay olmaydi**, chunki ularga kod
yetib bormaydi.

Ishga tushirishdan oldin `send_sms()` funksiyasini haqiqiy provayderga ulash kerak
(masalan [Eskiz.uz](https://eskiz.uz) yoki Play Mobile — O'zbekistonda keng
tarqalgan SMS shlyuzlari). Qolgan kod (`otp.py`, `notify.py`) o'zgarishsiz
ishlayveradi, chunki ular faqat shu bitta funksiyani chaqiradi. Agar kerak bo'lsa,
shu integratsiyani alohida so'rab qiling.

---

## 1. Server talablari

- Ubuntu 22.04/24.04 (yoki boshqa zamonaviy Linux) VPS, kamida 1 GB RAM.
- Domen nomi (ixtiyoriy, lekin HTTPS uchun kerak) — `A` yozuvi server IP'siga yo'naltirilgan.
- Docker va Docker Compose plugin:
  ```bash
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker $USER   # keyin qayta kiring (logout/login)
  ```

## 2. Kodni serverga olib kelish

```bash
git clone https://github.com/abdulloxon2005/ustabor.git
cd ustabor
```

## 3. Muhit sozlamalarini (`.env`) tayyorlash

```bash
cp backend/.env.production.example backend/.env
```

`backend/.env` faylini oching va **MAJBURIY** maydonlarni to'ldiring:

- `SECRET_KEY` — generatsiya qiling:
  ```bash
  docker compose run --rm backend python -c "import secrets; print(secrets.token_hex(32))"
  ```
- `CORS_ORIGINS` — haqiqiy domeningiz, masalan `https://ustabor.uz`.
- `SEED_ADMIN_PHONE` va `SEED_ADMIN_PASSWORD` — admin akkaunt uchun kuchli parol
  (standart `admin12345` bilan qolsa, seed skripti ataylab ishdan chiqadi).
- Ixtiyoriy: `YANDEX_GEOCODER_API_KEY`, `YANDEX_MAPS_JS_API_KEY` (xarita funksiyalari
  uchun), `FCM_PROJECT_ID`/`FCM_ACCESS_TOKEN` (push bildirishnomalar uchun).

`backend/.env` hech qachon git'ga qo'shilmaydi (`.gitignore`'da).

## 4. Ishga tushirish

```bash
docker compose build
docker compose up -d
```

Birinchi marta ishga tushganda backend konteyneri avtomatik `alembic upgrade head`
ni bajaradi (bazani yaratadi/yangilaydi), shundan keyingina serverni ko'taradi.

Tekshirish:

```bash
curl http://localhost/api/v1/health
# {"status":"ok","database":"ok","app":"UstaBor","environment":"production"}
```

Brauzerda `http://SERVER-IP/` ni oching — frontend ko'rinishi kerak.

## 5. Boshlang'ich ma'lumotlar (admin + kategoriyalar)

```bash
docker compose exec backend python -m scripts.seed
```

`ENVIRONMENT=production` bo'lgani uchun demo mijoz/usta yaratilmaydi — faqat admin
akkaunt va kategoriyalar ro'yxati tayyorlanadi.

## 6. HTTPS (Let's Encrypt / Certbot)

Domen DNS orqali server IP'siga yo'naltirilgan bo'lishi va 1–5-bosqichlar
bajarilgan (sayt HTTP orqali ishlayotgan) bo'lishi kerak.

```bash
docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d sizning-domeningiz.uz -d www.sizning-domeningiz.uz \
  --email sizning-emailingiz@example.com --agree-tos --no-eff-email
```

Sertifikat olingach:

1. `frontend/nginx-ssl.conf.example` faylini oching, `SIZNING-DOMENINGIZ.uz`
   o'rniga haqiqiy domeningizni qo'ying.
2. Shu faylni `frontend/nginx.conf` sifatida saqlang (eskisini almashtiring).
3. Qayta quring va ishga tushiring:
   ```bash
   docker compose build frontend
   docker compose up -d frontend
   ```

Endi sayt `https://sizning-domeningiz.uz` orqali ishlaydi va HTTP so'rovlar
HTTPS'ga avtomatik yo'naltiriladi.

**Sertifikatni yangilash** (3 oyda bir marta muddati tugaydi) — serverda cron
sozlang:

```bash
# crontab -e
0 3 1 * * cd /path/to/ustabor && docker compose run --rm certbot renew --quiet && docker compose restart frontend
```

## 7. Zaxira nusxa (backup)

```bash
docker compose exec backend python -m scripts.backup_db
```

Fayl serverdagi `backend/backups/` papkasiga yoziladi (docker-compose.yml orqali
konteyner bilan bog'langan) — shuning uchun to'g'ridan-to'g'ri shu papkadan
`rsync`/`scp` bilan serverdan tashqariga muntazam ko'chirib turish kifoya.
Avtomatlashtirish uchun cron'ga qo'shing:

```bash
# crontab -e — har kuni soat 03:00 da
0 3 * * * cd /path/to/ustabor && docker compose exec -T backend python -m scripts.backup_db
```

## 8. Yangilash (yangi versiya chiqqanda)

```bash
git pull
docker compose build
docker compose up -d
```

Migratsiyalar avtomatik qo'llanadi (entrypoint). Baza va yuklangan rasmlar
tomlarda saqlangani uchun yo'qolmaydi.

## 9. Loglarni ko'rish

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

## 10. Xavfsizlik eslatmalari

- Faqat kerakli portlarni oching: `sudo ufw allow 22,80,443/tcp && sudo ufw enable`.
- SSH'ga parol bilan emas, kalit (key) bilan kiring; root login'ni o'chiring.
- `backend/.env` faylini hech qachon git'ga qo'shmang yoki boshqa joyga yubormang —
  u `SECRET_KEY` va admin parolini o'z ichiga oladi.
- `ENVIRONMENT=production` bo'lgani uchun `/docs`, `/redoc`, `/openapi.json`
  avtomatik o'chirilgan (`backend/app/main.py`).
