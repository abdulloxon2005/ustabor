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
from app.models.enums import OfferStatus


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

      score = W_RATING * bayes_norm + W_DISTRICT * district_bonus + W_NEW * new_bonus

    Yangi usta bonusi (0.15 * 0.5 = 0.075) reyting vaznidan (0.6 * ~0.8 = 0.48)
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

    return (
        settings.MATCH_W_RATING * bayes_norm
        + settings.MATCH_W_DISTRICT * district_bonus
        + settings.MATCH_W_NEW_BONUS * new_bonus
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
) -> list[MasterProfile]:
    """eligible_masters + score bo'yicha tartiblash (katta -> kichik, id tie-break)."""
    masters = eligible_masters(db, order, exclude_master_ids)
    g_avg = global_average(db)
    return sorted(
        masters,
        key=lambda m: (-score_master(m, order, g_avg), m.id),
    )


def best_master(
    db: Session,
    order: Order,
    exclude_master_ids: set[int] | None = None,
) -> MasterProfile | None:
    """Eng yuqori skorli usta yoki None."""
    ranked = rank_masters(db, order, exclude_master_ids)
    return ranked[0] if ranked else None


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
    )
    if order is not None:
        stmt = stmt.where(OrderOffer.order_id == order.id)
    result = db.execute(stmt)
    return result.rowcount


def _already_offered_ids(db: Session, order: Order) -> set[int]:
    """Buyurtmaga allaqachon taklif yuborilgan ustalar id lari (har qanday status)."""
    return set(
        db.scalars(
            select(OrderOffer.master_id).where(OrderOffer.order_id == order.id)
        )
    )


def offer_next(
    db: Session,
    order: Order,
    actor: User,
) -> OrderOffer | None:
    """Automatic rejim: navbatdagi eng yaxshi ustaga taklif yuboradi.

    Avval muddati o'tganlarni tozalaydi, keyin allaqachon taklif
    yuborilganlarni istisno qilib, eng yaxshi ustani topadi.
    Hech kim qolmasa None qaytaradi. COMMIT QILMAYDI.
    """
    expire_stale_offers(db, order)
    exclude = _already_offered_ids(db, order)
    top = best_master(db, order, exclude)
    if top is None:
        return None
    return create_offer(db, order, top)
