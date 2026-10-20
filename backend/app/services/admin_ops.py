"""Admin amallari va hisobotlar xizmati.

Barcha funksiyalar COMMIT QILMAYDI — commit chaqiruvchida.
Buyurtma holati faqat order_flow.assign_master() orqali o'zgaradi.
"""

from datetime import date, datetime, time
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Category,
    MasterProfile,
    MasterService,
    Order,
    OrderOffer,
    OrderStatusHistory,
    Payment,
    User,
)
from app.models.enums import OfferStatus, OrderStatus, Role
from app.services import order_flow, pricing


class ReportOrderItem(dict):
    """Hisobotidagi buyurtma ma'lumotlari: ham dict, ham atribut orqali kirish mumkin."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'ReportOrderItem' has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class CommissionsReport(tuple):
    """Komissiyalar hisoboti: tuple unpacking (total, gross, comm, orders)
    va dict / atribut orqali kirishni qo'llab-quvvatlaydi.
    """

    def __new__(cls, total: int, gross: int, commission: int, orders: list[ReportOrderItem]):
        return super().__new__(cls, (total, gross, commission, orders))

    @property
    def total_completed_orders(self) -> int:
        return self[0]

    @property
    def total_orders(self) -> int:
        return self[0]

    @property
    def total(self) -> int:
        return self[0]

    @property
    def gross_total(self) -> int:
        return self[1]

    @property
    def commission_total(self) -> int:
        return self[2]

    @property
    def orders(self) -> list[ReportOrderItem]:
        return self[3]

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if hasattr(self, key):
                return getattr(self, key)
            raise KeyError(key)
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_completed_orders": self.total_completed_orders,
            "total_orders": self.total_orders,
            "gross_total": self.gross_total,
            "commission_total": self.commission_total,
            "orders": self.orders,
        }


def admin_assign_master(
    db: Session,
    order_id: int,
    master_profile_id: int,
    admin: User,
) -> Order:
    """Admin tomonidan ustani buyurtmaga biriktirish. COMMIT QILMAYDI.

    Qoidalar:
      - Faqat admin (Role.ADMIN) bajara oladi (aks holda 403).
      - Buyurtma mavjud bo'lishi va holati SEARCHING bo'lishi shart (aks holda 409).
      - Usta profili mavjud bo'lishi (aks holda 404), tasdiqlangan (is_approved),
        band bo'lmagan (is_available), foydalanuvchisi faol (user.is_active),
        va buyurtma kategoriyasi bo'yicha xizmati (MasterService) bo'lishi shart (aks holda 409/422).
      - order_flow.assign_master() chaqiriladi (atomik UPDATE).
      - OrderOffer mavjud bo'lsa accepted qilinadi, bo'lmasa accepted holatda yaratiladi.
      - pricing.apply_fixed_price() chaqiriladi (qat'iy narx bo'lsa agreed_price o'rnatiladi).
      - Ikkinchi biriktirish urinishi 409 qaytaradi.
    """
    if admin is None or admin.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")

    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")
    if order.status != OrderStatus.SEARCHING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Buyurtma qidiruv holatida emas",
        )

    master = db.get(MasterProfile, master_profile_id)
    if master is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usta profili topilmadi")
    if not master.is_approved:
        raise HTTPException(status.HTTP_409_CONFLICT, "Usta tasdiqlanmagan")
    if not master.is_available:
        raise HTTPException(status.HTTP_409_CONFLICT, "Usta band yoki faol emas")
    if master.user is None or not master.user.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Usta foydalanuvchisi faol emas")
    if master.city.strip().lower() != order.city.strip().lower():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Usta boshqa shaharda joylashgan",
        )

    service = db.scalar(
        select(MasterService).where(
            MasterService.master_id == master_profile_id,
            MasterService.category_id == order.category_id,
        )
    )
    if service is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Usta ushbu toifadagi xizmatni ko'rsatmaydi",
        )

    # Atomik biriktirish
    order = order_flow.assign_master(db, order_id, master_profile_id, actor=admin)

    # OrderOffer tarixi mos bo'lishi uchun tekshirib ACCEPTED holatga keltiramiz
    offer = db.scalar(
        select(OrderOffer).where(
            OrderOffer.order_id == order_id,
            OrderOffer.master_id == master_profile_id,
        )
    )
    if offer is None:
        offer = OrderOffer(
            order_id=order_id,
            master_id=master_profile_id,
            status=OfferStatus.ACCEPTED,
        )
        db.add(offer)
    else:
        offer.status = OfferStatus.ACCEPTED
    db.flush()

    # Agar xizmat fixed bo'lsa narxni qo'llash
    pricing.apply_fixed_price(db, order)

    return order


def set_user_active(
    db: Session,
    target_user_id: int,
    is_active: bool,
    admin: User,
) -> User:
    """Foydalanuvchini bloklash yoki blokdan chiqarish. COMMIT QILMAYDI.

    Qoidalar:
      - Faqat admin bajara oladi (aks holda 403).
      - Mavjud bo'lmagan foydalanuvchi -> 404.
      - Admin akkauntini yoki o'zining akkauntini o'zgartirish rad etiladi -> 409.
    """
    if admin is None or admin.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")

    target_user = db.get(User, target_user_id)
    if target_user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    if target_user.role == Role.ADMIN or target_user.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Adminni bloklab bo'lmaydi")

    target_user.is_active = bool(is_active)
    db.flush()
    return target_user


def _parse_date(d: Any, is_end: bool = False) -> datetime | None:
    if d is None:
        return None
    if isinstance(d, str):
        d = d.strip()
        if not d:
            return None
        # YYYY-MM-DD yoki ISO format
        try:
            dt = datetime.fromisoformat(d)
            if is_end and len(d) == 10:
                dt = datetime.combine(dt.date(), time.max)
        except ValueError:
            try:
                dt_date = date.fromisoformat(d)
            except ValueError:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "Sana formati noto'g'ri (YYYY-MM-DD talab qilinadi)",
                )
            dt = datetime.combine(dt_date, time.max if is_end else time.min)
        return dt
    if isinstance(d, datetime):
        return d
    if isinstance(d, date):
        return datetime.combine(d, time.max if is_end else time.min)
    return None


def commissions_report(
    db: Session,
    date_from: datetime | date | str | None = None,
    date_to: datetime | date | str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> CommissionsReport:
    """Yakunlangan buyurtmalar va komissiyalar hisoboti. COMMIT QILMAYDI.

    Faqat yakunlangan buyurtmalarni hisoblaydi, butun sonli arifmetika.
    Qaytaradi: (total_completed_orders, gross_total, commission_total, orders).
    """
    dt_from = _parse_date(date_from, is_end=False)
    dt_to = _parse_date(date_to, is_end=True)

    # Yakunlangan vaqtini order_status_history jadvalidan (to_status=completed) olamiz
    history_subq = (
        select(
            OrderStatusHistory.order_id,
            func.max(OrderStatusHistory.created_at).label("completed_at"),
        )
        .where(OrderStatusHistory.to_status == OrderStatus.COMPLETED)
        .group_by(OrderStatusHistory.order_id)
        .subquery()
    )

    completed_at_col = func.coalesce(history_subq.c.completed_at, Order.created_at)

    base_query = (
        select(Order, completed_at_col.label("completed_at"))
        .outerjoin(history_subq, Order.id == history_subq.c.order_id)
        .where(Order.status == OrderStatus.COMPLETED)
        .options(
            selectinload(Order.category),
            selectinload(Order.master).selectinload(MasterProfile.user),
        )
    )

    if dt_from is not None:
        base_query = base_query.where(completed_at_col >= dt_from)
    if dt_to is not None:
        base_query = base_query.where(completed_at_col <= dt_to)

    all_matches = db.execute(base_query).all()

    total_completed_orders = len(all_matches)
    gross_total = 0
    commission_total = 0

    for ord_obj, _ in all_matches:
        agreed = ord_obj.agreed_price or 0
        gross_total += agreed
        if ord_obj.commission_amount is not None:
            commission_total += ord_obj.commission_amount
        else:
            crate = ord_obj.commission_rate if ord_obj.commission_rate is not None else 10
            commission_total += (agreed * crate) // 100

    # Eng yangi yakunlanganlar birinchi (completed_at desc, id desc)
    sorted_matches = sorted(
        all_matches,
        key=lambda pair: (pair[1] or pair[0].created_at, pair[0].id),
        reverse=True,
    )

    paged = (
        sorted_matches[offset : offset + limit]
        if limit is not None
        else sorted_matches[offset:]
    )

    # To'lovlarni bitta so'rovda yuklaymiz
    paged_order_ids = [ord_obj.id for ord_obj, _ in paged]
    payments_map: dict[int, Payment] = {}
    if paged_order_ids:
        pmts = db.scalars(
            select(Payment).where(Payment.order_id.in_(paged_order_ids))
        ).all()
        for pmt in pmts:
            payments_map[pmt.order_id] = pmt

    orders_list: list[ReportOrderItem] = []
    for ord_obj, comp_at in paged:
        agreed = ord_obj.agreed_price or 0
        crate = ord_obj.commission_rate if ord_obj.commission_rate is not None else 10
        if ord_obj.commission_amount is not None:
            comm_amt = ord_obj.commission_amount
        else:
            comm_amt = (agreed * crate) // 100
        master_net = agreed - comm_amt

        pmt = payments_map.get(ord_obj.id)
        pmt_amount = pmt.amount if pmt else None
        pmt_status = (
            pmt.status.value
            if pmt and hasattr(pmt.status, "value")
            else (pmt.status if pmt else None)
        )

        cat_name = ord_obj.category.name if ord_obj.category else ""
        m_name = (
            ord_obj.master.user.full_name
            if ord_obj.master and ord_obj.master.user
            else ""
        )

        item = ReportOrderItem(
            id=ord_obj.id,
            completed_at=comp_at,
            completed_date=comp_at,
            category_name=cat_name,
            master_name=m_name,
            agreed_price=agreed,
            commission_rate=crate,
            commission_amount=comm_amt,
            master_net=master_net,
            payment_amount=pmt_amount,
            payment_status=pmt_status,
        )
        orders_list.append(item)

    return CommissionsReport(
        total=total_completed_orders,
        gross=gross_total,
        commission=commission_total,
        orders=orders_list,
    )
