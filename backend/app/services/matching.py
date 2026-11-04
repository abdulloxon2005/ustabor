"""Ustalarni tanlash va takliflar (offers) mantig'i.

Scoring formulasi (score_master docstring'ida batafsil):
  score = W_RATING * bayes_norm + W_DISTRICT * district_bonus + W_NEW * new_bonus

  - bayes_norm: Bayesian average [0..1] oraliqda normallashtirilgan (5-ballik shkala).
  - district_bonus: 1.0 agar usta va buyurtma bir tumanda, 0.5 agar faqat bir shaharda.
  - new_bonus: 0.5 agar usta yangi (rating_count < threshold), 0.0 aks holda.
    Bu yangi ustalarni O'RTAGA qo'yadi: ular eng pastda emas, lekin tajribali
    ustalarning reyting ustuvorligini buzolmaydi (w_new << w_rating).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import MasterProfile, MasterService, Order, OrderOffer, Review, User
from app.models.enums import OfferStatus, OrderStatus, SelectionMode
from app.services import geo, notify

# Shu masofadan (km) uzoqda masofa bonusi 0 ga tushadi (chiziqli pasayish)
DISTANCE_DECAY_KM = 20.0


# ---------- Bayes reyting ----------

def bayes_rating(
    rating_avg: float,
    rating_count: int,
    global_avg: float,
    m: int | None = None,
) -> float:
    """Bayesian average: (v/(v+m))*R + (m/(v+m))*C.

    R = rating_avg, v = rating_count, C = global_avg, m = prior (pseudo-count).
    Agar v=0, natija aynan C bo'ladi.
    """
    if m is None:
        m = settings.MATCH_RATING_PRIOR_COUNT
    v = rating_count
    if v + m == 0:
        return global_avg
    return (v / (v + m)) * rating_avg + (m / (v + m)) * global_avg


def global_average(db: Session) -> float:
    """Barcha sharhlarning o'rtacha reytingi; sharhlar yo'q bo'lsa default."""
    avg = db.scalar(select(func.avg(Review.rating)))
    return float(avg) if avg is not None else settings.MATCH_DEFAULT_GLOBAL_AVG


# ---------- Scoring (DB-siz, sof funksiya) ----------

def score_master(master: MasterProfile, order: Order, global_avg: float) -> float:
    """Ustaning buyurtmaga nisbatan skori (katta = yaxshi).

    Formula:
      bayes = bayes_rating(master.rating_avg, master.rating_count, global_avg)
      bayes_norm = bayes / 5.0   (5 - maksimal ball, natija [0..1])
      district_bonus = 1.0 agar tuman mos, 0.5 agar faqat shahar mos, 0 aks holda
      new_bonus = 0.5 agar rating_count < MATCH_NEW_MASTER_THRESHOLD, 0.0 aks holda
      distance_bonus = max(0, 1 - masofa_km / DISTANCE_DECAY_KM) agar ikkala tomonda
        koordinata bo'lsa, aks holda 0 (orqaga mos: koordinatasiz hamma eski
        natijani oladi).

      score = W_RATING * bayes_norm + W_DISTRICT * district_bonus
            + W_NEW * new_bonus + W_DISTANCE * distance_bonus

    Vaznlar yig'indisi = 1.0 (0.55 + 0.20 + 0.10 + 0.15).
    Yangi usta bonusi (0.10 * 0.5 = 0.05) reyting vaznidan (0.55 * ~0.8 = 0.44)
    ancha kichik, shuning uchun bitta 5 yulduzli sharh 50 ta 4.8 li ustadan
    oldinga o'ta olmaydi.
    """
    bayes = bayes_rating(master.rating_avg, master.rating_count, global_avg)
    bayes_norm = bayes / 5.0  # [0..1]

    # Joylashuv bonusi: buyurtma shahri doimiy (eligible_masters shaharga filtreydi),
    # shuning uchun shahar bonus har doim kamida 0.5.
    city_match = master.city.strip().lower() == order.city.strip().lower()
    district_match = city_match and master.district.strip().lower() == order.district.strip().lower()
    district_bonus = 1.0 if district_match else (0.5 if city_match else 0.0)

    # Yangi usta bonusi
    new_bonus = 0.5 if master.rating_count < settings.MATCH_NEW_MASTER_THRESHOLD else 0.0

    # Masofa bonusi: ikkala tomonda koordinata bo'lsagina hisoblanadi
    distance_bonus = 0.0
    if (
        master.location_sharing_enabled
        and
        master.latitude is not None
        and master.longitude is not None
        and order.latitude is not None
        and order.longitude is not None
    ):
        dist_km = geo.haversine_km(
            master.latitude, master.longitude, order.latitude, order.longitude
        )
        distance_bonus = max(0.0, 1.0 - dist_km / DISTANCE_DECAY_KM)

    return (
        settings.MATCH_W_RATING * bayes_norm
        + settings.MATCH_W_DISTRICT * district_bonus
        + settings.MATCH_W_NEW_BONUS * new_bonus
        + settings.MATCH_W_DISTANCE * distance_bonus
    )


# ---------- Ro'yxat va tartiblash ----------

def eligible_masters(
    db: Session,
    order: Order,
    exclude_master_ids: set[int] | None = None,
) -> list[MasterProfile]:
    """Buyurtmaga mos keluvchi ustalar: tasdiqlangan, band emas, user faol,
    buyurtma kategoriyasiga xizmati bor, shahar bir xil, exclude_ids da emas.
    """
    stmt = (
        select(MasterProfile)
        .join(User, User.id == MasterProfile.user_id)
        .where(
            MasterProfile.is_approved.is_(True),
            MasterProfile.is_available.is_(True),
            User.is_active.is_(True),
            func.lower(MasterProfile.city) == order.city.strip().lower(),
            exists().where(
                MasterService.master_id == MasterProfile.id,
                MasterService.category_id == order.category_id,
            ),
        )
        .options(selectinload(MasterProfile.user))
    )
    if exclude_master_ids:
        stmt = stmt.where(MasterProfile.id.not_in(exclude_master_ids))
    return list(db.scalars(stmt).all())


def rank_masters(
    db: Session,
    order: Order,
    exclude_master_ids: set[int] | None = None,
    radius_km: float | None = None,
) -> list[MasterProfile]:
    """eligible_masters + score bo'yicha tartiblash (katta -> kichik, id tie-break)."""
    masters = eligible_masters(db, order, exclude_master_ids)
    if radius_km is not None and order.latitude is not None and order.longitude is not None:
        masters = [
            m for m in masters
            if m.location_sharing_enabled
            and m.latitude is not None and m.longitude is not None
            and geo.haversine_km(order.latitude, order.longitude, m.latitude, m.longitude) <= radius_km
        ]
    g_avg = global_average(db)
    return sorted(
        masters,
        key=lambda m: (-score_master(m, order, g_avg), m.id),
    )


DISPATCH_RADII_KM = (5, 15, 30, 50)


def dispatch_next_wave(db: Session, order: Order) -> tuple[list[OrderOffer], str]:
    """Send one radius wave, excluding every master already offered this order.

    Caller owns commit. Existing atomically-claimed order flow decides the
    winner; this function only opens the next wave after pending offers resolve.
    """
    expire_stale_offers(db, order)
    # Sessions intentionally disable autoflush; caller may just have rejected
    # an offer, so persist pending status changes before counting open offers.
    db.flush()
    if order.status != OrderStatus.SEARCHING:
        return [], "assigned" if order.master_id else "closed"

    pending = db.scalar(select(func.count(OrderOffer.id)).where(
        OrderOffer.order_id == order.id, OrderOffer.status == OfferStatus.PENDING
    )) or 0
    if pending:
        return [], "waiting"

    excluded = _already_offered_ids(db, order)
    if order.latitude is None or order.longitude is None:
        candidates = rank_masters(db, order, excluded)
        radius = 999
    else:
        next_radius = next((r for r in DISPATCH_RADII_KM if r > order.dispatch_radius_km), None)
        if next_radius is None:
            candidates = rank_masters(db, order, excluded)
            # Final city-wide expansion also admits masters without shared GPS.
            radius = 999
        else:
            candidates = rank_masters(db, order, excluded, radius_km=next_radius)
            radius = next_radius
            # Masters who have not opted into live location still participate
            # as a city-wide fallback when the current GPS radius is empty.
            if not candidates:
                unknown = [m for m in eligible_masters(db, order, excluded)
                           if not m.location_sharing_enabled
                           or m.latitude is None or m.longitude is None]
                g_avg = global_average(db)
                candidates = sorted(unknown,
                                    key=lambda m: (-score_master(m, order, g_avg), m.id))

    order.dispatch_radius_km = radius
    if not candidates:
        return [], "exhausted"
    return [create_offer(db, order, master) for master in candidates], "offered"


# ---------- Takliflar (offers) ----------

def create_offer(db: Session, order: Order, master: MasterProfile) -> OrderOffer:
    """Yangi taklif yaratadi (status=pending, expires_at kelajakda). COMMIT QILMAYDI."""
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.OFFER_TTL_MINUTES)
    offer = OrderOffer(
        order_id=order.id,
        master_id=master.id,
        status=OfferStatus.PENDING,
        expires_at=expires,
    )
    db.add(offer)
    notify.notify_user(
        db,
        master.user_id,
        "new_offer",
        "Yangi taklif",
        (
            f"{order.category.name} — {order.customer.full_name}, "
            f"{order.city}, {order.district}"
        ),
        order_id=order.id,
    )
    return offer


def expire_stale_offers(db: Session, order: Order | None = None) -> int:
    """Muddati o'tgan pending takliflarni expired qilib belgilaydi. COMMIT QILMAYDI.

    order berilsa faqat o'sha buyurtmaning takliflari, aks holda hammasi.
    Qaytaradi: yangilangan qatorlar soni.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        update(OrderOffer)
        .where(
            OrderOffer.status == OfferStatus.PENDING,
            OrderOffer.expires_at < now,
        )
        .values(status=OfferStatus.EXPIRED)
        # SQLite'da saqlangan va hali commit qilinmagan obyektlardagi
        # timezone-aware/naive datetime aralashib ketishi mumkin (ORM "evaluate"
        # strategiyasi Python'da solishtiradi). Buyruq to'g'ridan-to'g'ri SQL
        # orqali bajariladi, keyin db.expire_all() keshni yangilaydi.
        .execution_options(synchronize_session=False)
    )
    if order is not None:
        stmt = stmt.where(OrderOffer.order_id == order.id)
    result = db.execute(stmt)
    if result.rowcount > 0:
        db.expire_all()
    return result.rowcount


def _already_offered_ids(db: Session, order: Order) -> set[int]:
    """Buyurtmaga allaqachon taklif yuborilgan ustalar id lari (har qanday status)."""
    return set(
        db.scalars(
            select(OrderOffer.master_id).where(OrderOffer.order_id == order.id)
        )
    )


def broadcast_offers(
    db: Session,
    order: Order,
    actor: User | None = None,
) -> list[OrderOffer]:
    """Automatic rejim: barcha mos (hali taklif olmagan) ustalarga BIR VAQTDA
    taklif yuboradi — "ochiq buyurtma": har bir usta o'z dashboardida ko'radi,
    birinchi qabul qilgani g'olib bo'ladi (order_flow.assign_master atomik
    UPDATE orqali boshqa hammaning takliflarini avtomatik rad etadi).

    Avval muddati o'tganlarni tozalaydi, keyin allaqachon taklif yuborilgan
    (har qanday holatdagi) ustalarni istisno qilib qolgan mos ustalarga yangi
    taklif yaratadi (reyting bo'yicha tartiblangan holda). COMMIT QILMAYDI.
    Qaytaradi: yangi yaratilgan takliflar ro'yxati.
    """
    expire_stale_offers(db, order)
    exclude = _already_offered_ids(db, order)
    masters = rank_masters(db, order, exclude)
    return [create_offer(db, order, m) for m in masters]


def rotate_stale_automatic_orders(
    db: Session, order: Order | None = None, customer_id: int | None = None
) -> int:
    """Muddati o'tgan takliflarni tozalaydi va automatic qidiruvdagi
    buyurtmalarga hali taklif olmagan yangi mos ustalar bo'lsa ularga ham
    taklif yuboradi (masalan, usta endigina tasdiqlangan yoki bo'sh bo'lgan
    bo'lsa). COMMIT QILMAYDI. Qaytaradi: yangi yaratilgan takliflar soni.
    """
    expire_stale_offers(db, order)

    stmt = select(Order).where(
        Order.status == OrderStatus.SEARCHING,
        Order.selection_mode == SelectionMode.AUTOMATIC,
    )
    if order is not None:
        stmt = stmt.where(Order.id == order.id)
    if customer_id is not None:
        stmt = stmt.where(Order.customer_id == customer_id)

    auto_orders = db.scalars(stmt).all()
    count = 0
    for ord_obj in auto_orders:
        offers, _ = dispatch_next_wave(db, ord_obj)
        count += len(offers)
    return count
