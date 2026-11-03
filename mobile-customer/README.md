# UstaBor — Mijozlar ilovasi (React Native / Expo)

Mavjud `backend` (FastAPI) uchun mijozlar mobil ilovasi. Ustalar ilovasi alohida qilinadi.

## Imkoniyatlar

- Kirish, OTP bilan ro'yxatdan o'tish, parolni tiklash va o'zgartirish
- Xizmat turlari, ustalarni qidirish, yaqin atrofdagi ustalar (joylashuv bo'yicha)
- Usta profili: xizmatlar, ish jadvali, rasmlar, sharhlar, sevimlilar
- Buyurtma yaratish (rasmlar, joylashuv, avtomatik yoki qo'lda usta tanlash)
- Buyurtma holati, narx takliflarini qabul qilish/rad etish, bekor qilish
- Usta bilan chat, baholash, shikoyat, bildirishnomalar

## Ishga tushirish

1. Backendni tarmoqqa ochiq holda ishga tushiring (telefon ulanishi uchun `0.0.0.0` kerak):

   ```powershell
   cd backend
   .\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. Ilovani ishga tushiring:

   ```powershell
   cd mobile-customer
   npm install
   npx expo start
   ```

   Telefondagi **Expo Go** ilovasi bilan QR-kodni skanerlang. Telefon va kompyuter **bir Wi-Fi** tarmog'ida bo'lishi shart.

Backend manzili Expo dev server IP'sidan avtomatik aniqlanadi (`src/config.ts`). Qo'lda berish uchun:

```powershell
$env:EXPO_PUBLIC_API_URL = "http://192.168.1.10:8000"; npx expo start
```

Windows xavfsizlik devori (Firewall) 8000 va 8081 portlarni bloklasa, ruxsat bering.

## Test ma'lumotlari

- Mijoz: `+998901111111` / `demo12345`
- SMS hozircha mock: ro'yxatdan o'tishdagi tasdiqlash kodi `backend/sms_outbox.log` faylining oxirgi qatorida.

## Tuzilma

```
src/
  api/        — fetch klient, endpointlar, TypeScript turlari
  auth/       — AuthContext (token SecureStore'da)
  components/ — umumiy UI komponentlar
  navigation/ — Auth stack, Main stack, pastki tablar
  screens/    — ekranlar
```

Ilova faqat `customer` rolidagi foydalanuvchilarni qabul qiladi.
