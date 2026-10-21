# SmartUsta (UstaBor) — Qo'lda sinash jadvali (Manual Test Sheet)

**Tayyorgarlik:**
1. `backend\` papkasidan virtual muhitni faollashtirib, baza va boshlang'ich ma'lumotlarni tayyorlang:
   ```cmd
   cd D:\BMI\ustabor\backend
   venv\Scripts\activate
   alembic upgrade head
   python -m scripts.seed
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
2. `frontend\` papkasidan statik serverni ishga tushiring:
   ```cmd
   cd D:\BMI\ustabor\frontend
   python -m http.server 5500
   ```
3. Brauzerda `http://localhost:5500/index.html` sahifasini oching va DevTools (`F12` -> Device Toolbar `Ctrl+Shift+M`) orqali ekran kengligini **360px** (masalan, 360×800) ga o'rnating.

**Demo akkauntlar (`scripts.seed`):**
- **Mijoz:** `+998901111111` / `demo12345` (Demo Mijoz)
- **Usta (kelishuv narxida santexnik):** `+998902222223` / `demo12345` (Bobur Tursunov, Toshkent, Chilonzor)
- **Usta (qat'iy narxda santexnik):** `+998902222221` / `demo12345` (Aziz Karimov, Toshkent, Chilonzor)
- **Admin:** `+998900000000` / `admin12345` (Administrator)

---

| step | account | page | action | expected result |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Mijoz (`+998901111111` / `demo12345`) | `login.html` -> `create-order.html` | `login.html` da mijoz sifatida kiring, `index.html` da **"Buyurtma berish"** (yoki **"Santexnik"**) ni bosing. `create-order.html` da Xizmat turi: **Santexnik**, Tavsif: `Oshxonada quvurdan suv oqmoqda`, Shahar: `Toshkent`, Tuman: `Chilonzor`, Manzil: `Chilonzor 7-kvartal, 14-uy`, Usta tanlash usuli: **"O'zim tanlayman"** ni tanlab, **"Buyurtma berish"** tugmasini bosing. | Buyurtma yaratiladi (`status = searching`) va brauzer avtomatik ravishda `masters.html?category_id=...&city=Toshkent&district=Chilonzor&order_id=...` sahifasiga o'tadi. |
| 2 | Mijoz (`+998901111111`) | `masters.html` | Ro'yxatda **Bobur Tursunov** (`Santexnik — Narx kelishiladi`) kartochkasidagi **"Tanlash"** tugmasini bosing va tasdiqlash oynasida **OK** ni bosing. | Ustaga taklif yuboriladi va brauzer `my-orders.html` sahifasiga o'tadi; buyurtma kartochkasida **"Qidirilmoqda"** nishoni va **"Usta javobi kutilmoqda"** yozuvi ko'rinadi. |
| 3 | Usta (`+998902222223` / `demo12345`) | `login.html` -> `master-dashboard.html` | Chiqish qilib (yoki ikkinchi oynada) **Bobur Tursunov** (`+998902222223` / `demo12345`) bilan kiring. `master-dashboard.html` da **"Yangi takliflar"** bo'limidagi buyurtma kartochkasida **"Qabul qilish"** tugmasini bosing va tasdiqlang. | Buyurtma **"Yangi takliflar"** dan **"Faol ishlar"** bo'limiga o'tadi, holati **"Biriktirildi"** bo'ladi va **"Narx taklif qilish"** formasi ochiladi. |
| 4 | Usta (`+998902222223`) | `master-dashboard.html` | **"Faol ishlar"** dagi buyurtma ichida **"Narx (so'm)"** maydoniga `200000`, **"Izoh"** maydoniga `Quvur va kran almashtirish` deb yozib, **"Yuborish"** tugmasini bosing. | Forma ustida **"Mijoz javobi kutilmoqda"** va **"Taklif qilingan narx: 200 000 so'm (Quvur va kran almashtirish)"** banneri paydo bo'ladi. |
| 5 | Mijoz (`+998901111111`) | `my-orders.html` | Mijoz akkauntiga qaytib `my-orders.html` ni yangilang, buyurtma kartochkasidagi **"Usta narx taklifi: 200 000 so'm"** blokida **"Tasdiqlash"** tugmasini bosing va tasdiqlang. | Taklif qabul qilinadi, kartochkada **"Kelishilgan narx: 200 000 so'm"** ko'rinadi. Mijozga hech qayerda `commission_amount` yoki ustaning sof daromadi ko'rsatilmaydi. |
| 6 | Usta (`+998902222223`) | `master-dashboard.html` | Usta panelini yangilang; **"Faol ishlar"** da **"Kelishilgan narx: 200 000 so'm"** va **"Ishni boshlash"** tugmasi chiqadi. **"Ishni boshlash"** tugmasini bosing. | Buyurtma holati nishoni **"Jarayonda"** (`in_progress`) ga o'zgaradi va **"Yakunlash"** tugmasi paydo bo'ladi. |
| 7 | Usta (`+998902222223`) | `master-dashboard.html` | **"Yakunlash"** tugmasini bosing va tasdiqlash oynasida **OK** ni bosing. | Brauzer xabarida **"Komissiya: 20 000 so'm, sizga: 180 000 so'm"** chiqadi. **"Daromadlar hisobi"** kartochkasida: Bajarilgan ishlar `1`, Jami tushum `200 000 so'm`, Komissiya `20 000 so'm`, Sof daromad `180 000 so'm` ko'rsatiladi. |
| 8 | Mijoz (`+998901111111`) | `my-orders.html` -> `order-detail.html` -> `masters.html` | Mijoz sifatida `my-orders.html` dan **"Batafsil ko'rish →"** orqali `order-detail.html` ga kiring. **"Xizmat haqida sharh qoldiring"** formasida 5 yulduz (`★`) va `Ish juda toza bajarildi!` izohini kiritib **"Sharh yuborish"** ni bosing, so'ng `masters.html` da Bobur Tursunov kartochkasini tekshiring. | `order-detail.html` da holat **"Yakunlandi"**, **"Holat tarixi"** da 4 ta qadam (`Qidirilmoqda -> Biriktirildi -> Jarayonda -> Yakunlandi`), komissiya ko'rinmaydi, **"Sizning sharhingiz (★ 5 / 5)"** paydo bo'ladi. `masters.html` da Bobur Tursunovda **"★ 5.0 (1 sharh)"** va **"Sharhlar (1) ▼"** ichida sharh matni ko'rinadi. |
| 9 | Admin (`+998900000000` / `admin12345`) | `login.html` -> `admin.html` | Admin sifatida kiring. `admin.html` da avval **"Buyurtmalar"** tabini, so'ng **"Komissiya"** tabini oching. | **"Buyurtmalar"** tabida yakunlangan buyurtmada Narx `200 000 so'm`, Komissiya `20 000 so'm`, Holat **"Yakunlandi"** ko'rinadi. **"Komissiya"** tabida Bajarilgan buyurtmalar `1`, Jami tushum `200 000 so'm`, Jami komissiya `20 000 so'm`, jadvalda Stavka `10%`, Usta sof `180 000 so'm`, To'lov holati `To'langan (200 000 so'm)` ko'rinadi. |
| 10 | Mehmon (kirmagan) | `login.html` | Telefon maydoniga `+998901111111`, Parol maydoniga noto'g'ri parol (`xatoparol123`) kiritib **"Kirish"** tugmasini bosing. | Sahifada qizil xatolik matni: **"Telefon yoki parol noto'g'ri"** chiqadi, sessiya saqlanmaydi. |
| 11 | Yangi Usta (`+998903334455` / `usta12345`) | `register.html` -> `master-profile.html` -> `masters.html` | `register.html` da **"Usta"** rolini tanlab, Ism: `Sardor Usta`, Telefon: `+998903334455`, Parol: `usta12345` bilan ro'yxatdan o'ting. `master-dashboard.html` dan **"Profilni yaratish"** (`master-profile.html`) ga o'tib, Shahar: `Toshkent`, Tuman: `Chilonzor`, Bio kiritib saqlang va **Santexnik** (`Qat'iy narx: 130000`) xizmatini saqlang. | `master-profile.html` yuqorisida sariq **"Admin tasdiqlashini kutmoqda"** banneri turadi. `masters.html` sahifasida **Sardor Usta** hali mijozlarga ko'rinmaydi. |
| 12 | Admin (`+998900000000`) -> Yangi Usta | `admin.html` -> `master-profile.html` -> `masters.html` | Admin sifatida `admin.html` -> **"Foydalanuvchilar"** tabiga o'ting, **Sardor Usta** qatorida (`Kutilmoqda · ★ 0.0 (0)`) **"Tasdiqlash"** tugmasini bosing va tasdiqlang. So'ng `masters.html` va usta profilini tekshiring. | Admin jadvalida holat `Tasdiqlangan` bo'ladi. Usta `master-profile.html` da yashil **"Tasdiqlangan"** bannerini ko'radi va `masters.html` ro'yxatida **Sardor Usta** paydo bo'ladi. |
| 13 | Admin (`+998900000000`) -> Bloklangan foydalanuvchi | `admin.html` -> `login.html` | Admin sifatida `admin.html` -> **"Foydalanuvchilar"** tabida **Sardor Usta** (`+998903334455`) qatoridagi **"Bloklash"** tugmasini bosing va tasdiqlang. So'ng `login.html` da `+998903334455` / `usta12345` bilan kirishga urining (keyin Admin orqali **"Faollashtirish"** ni bosing). | Jadvalda foydalanuvchi holati **"Bloklangan"** bo'ladi; mavjud sessiya `401` olib `login.html` ga qaytadi; qayta kirishda **"Akkaunt bloklangan"** xatosi chiqadi. **"Faollashtirish"** bosilgach qayta kira oladi. |
| 14 | Mehmon / Mijoz / Usta / Admin | Barcha sahifalar (`index.html`, `login.html`, `register.html`, `masters.html`, `create-order.html`, `my-orders.html`, `order-detail.html`, `profile.html`, `master-dashboard.html`, `master-profile.html`, `admin.html`) | Brauzer kengligini **360px** da ushlab turgan holda har bir sahifani navbat bilan ochib, yuqoridan pastgacha aylantiring. | Hech bir sahifada gorizontal skroll (`horizontal overflow`) yo'q; tugmalar va formalar ekranga to'liq sig'adi; pastki navigatsiya (`bottom-nav`) qulay joylashgan; `admin.html` jadvallari 360px da ustun-ustun (`stack` kartochka) ko'rinishiga o'tadi. |
| 15 | Mijoz yoki Mehmon | `index.html` / `my-orders.html` | Backend terminalida `uvicorn` serverni to'xtating (`Ctrl+C`) va sahifani yangilang. Xatolik chiqqach, `uvicorn` ni qayta ishga tushiring va sahifadagi **"Qayta urinish"** tugmasini bosing. | Server o'chiqligida **"Serverga ulanib bo'lmadi"** xabari va **"Qayta urinish"** tugmasi ko'rinadi. Server yoqilib **"Qayta urinish"** bosilgach, ma'lumotlar xatosiz qayta yuklanadi. |
