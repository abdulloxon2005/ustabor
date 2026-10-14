"""Boshlang'ich ma'lumotlar: admin, 5 kategoriya, 3 demo usta, 1 demo mijoz.

Ishga tushirish (backend papkasidan):  python -m scripts.seed
Skript qayta ishga tushirilsa, mavjud yozuvlarni ikkilantirmaydi.
"""

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Category, MasterProfile, MasterService, User
from app.models.enums import PricingType, Role

DEFAULT_ADMIN_PASSWORD = "admin12345"
DEMO_PASSWORD = "demo12345"

CATEGORIES = [
    ("Santexnik", "santexnik"),
    ("Elektrik", "elektrik"),
    ("Konditsioner ustasi", "konditsioner"),
    ("Maishiy texnika ta'miri", "maishiy-texnika"),
    ("Ta'mirlash va qurilish", "tamirlash"),
]

CUSTOMER = {"phone": "+998901111111", "full_name": "Demo Mijoz"}

# Aziz va Bobur bir tumanda (Chilonzor): automatic rejimni sinash uchun
MASTERS = [
    {
        "phone": "+998902222221",
        "full_name": "Aziz Karimov",
        "bio": "10 yillik tajribali santexnik",
        "city": "Toshkent",
        "district": "Chilonzor",
        "services": [
            ("santexnik", PricingType.FIXED, 150_000),
            ("elektrik", PricingType.QUOTE, None),
        ],
    },
    {
        "phone": "+998902222222",
        "full_name": "Jasur Rahimov",
        "bio": "Elektrik va konditsioner o'rnatish",
        "city": "Toshkent",
        "district": "Yunusobod",
        "services": [
            ("elektrik", PricingType.FIXED, 120_000),
            ("konditsioner", PricingType.QUOTE, None),
        ],
    },
    {
        "phone": "+998902222223",
        "full_name": "Bobur Tursunov",
        "bio": "Santexnika va maishiy texnika ta'miri",
        "city": "Toshkent",
        "district": "Chilonzor",
        "services": [
            ("santexnik", PricingType.QUOTE, None),
            ("maishiy-texnika", PricingType.FIXED, 100_000),
        ],
    },
]


def get_or_create_user(db, phone: str, full_name: str, role: Role, password: str):
    user = db.scalar(select(User).where(User.phone == phone))
    if user:
        return user, False
    user = User(
        phone=phone,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
    )
    db.add(user)
    db.flush()  # id olish uchun
    return user, True


def main() -> None:
    is_prod = settings.ENVIRONMENT == "production"
    if is_prod and settings.SEED_ADMIN_PASSWORD == DEFAULT_ADMIN_PASSWORD:
        raise SystemExit(
            "Production'da SEED_ADMIN_PASSWORD ni .env da o'zgartiring!"
        )

    created = []

    with SessionLocal() as db:
        # 1. Admin (faqat shu skript orqali yaratiladi)
        _, new = get_or_create_user(
            db,
            settings.SEED_ADMIN_PHONE,
            "Administrator",
            Role.ADMIN,
            settings.SEED_ADMIN_PASSWORD,
        )
        if new:
            created.append("admin")

        # 2. Kategoriyalar
        for name, slug in CATEGORIES:
            if not db.scalar(select(Category).where(Category.slug == slug)):
                db.add(Category(name=name, slug=slug))
                created.append(f"kategoriya: {name}")
        db.flush()

        # Demo ma'lumotlar productionga qo'yilmaydi
        if not is_prod:
            # 3. Demo mijoz
            _, new = get_or_create_user(
                db, CUSTOMER["phone"], CUSTOMER["full_name"], Role.CUSTOMER, DEMO_PASSWORD
            )
            if new:
                created.append("demo mijoz")

            # 4. Demo ustalar
            cats = {c.slug: c for c in db.scalars(select(Category))}
            for m in MASTERS:
                user, new = get_or_create_user(
                    db, m["phone"], m["full_name"], Role.MASTER, DEMO_PASSWORD
                )
                profile = db.scalar(
                    select(MasterProfile).where(MasterProfile.user_id == user.id)
                )
                if profile:
                    continue
                profile = MasterProfile(
                    user_id=user.id,
                    bio=m["bio"],
                    city=m["city"],
                    district=m["district"],
                    is_available=True,
                    is_approved=True,  # demo ustalar tasdiqlangan
                )
                db.add(profile)
                db.flush()
                for slug, pricing_type, price in m["services"]:
                    db.add(
                        MasterService(
                            master_id=profile.id,
                            category_id=cats[slug].id,
                            pricing_type=pricing_type,
                            base_price=price,
                        )
                    )
                created.append(f"usta: {m['full_name']}")

        db.commit()

    if created:
        print("Qo'shildi:")
        for item in created:
            print("  -", item)
    else:
        print("Hammasi allaqachon bor, yangi narsa qo'shilmadi.")

    print("\nKirish ma'lumotlari:")
    print(f"  Admin : {settings.SEED_ADMIN_PHONE} / {settings.SEED_ADMIN_PASSWORD}")
    if not is_prod:
        print(f"  Mijoz : {CUSTOMER['phone']} / {DEMO_PASSWORD}")
        for m in MASTERS:
            print(f"  Usta  : {m['phone']} / {DEMO_PASSWORD}  ({m['full_name']})")


if __name__ == "__main__":
    main()