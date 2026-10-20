from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.db.session import get_db
from app.models import (
    Category,
    MasterProfile,
    Order,
    Payment,
    Review,
    User,
)
from app.models.enums import OrderStatus, Role
from app.schemas.admin import (
    AdminAssignIn,
    AdminOrderDetailOut,
    AdminOrderListItem,
    AdminPaymentOut,
    AdminReviewOut,
    AdminUserItem,
    CommissionOrderItem,
    CommissionsReportOut,
    UserStatusIn,
)
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate, slugify
from app.schemas.master import ApprovalIn, ApprovalOut
from app.schemas.order import HistoryOut, OfferOut
from app.schemas.quote import QuoteOut
from app.services import admin_ops

# Router darajasida: admindan boshqa hech kim kira olmaydi
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)

SLUG_TAKEN = "Bu slug allaqachon mavjud"


def _admin_order_detail_out(order: Order, db: Session) -> AdminOrderDetailOut:
    master_name = None
    if order.master and order.master.user:
        master_name = order.master.user.full_name
    elif order.master_id:
        mp = db.get(MasterProfile, order.master_id)
        if mp:
            u = db.get(User, mp.user_id)
            master_name = u.full_name if u else None

    # Offers
    offers = []
    for off in order.offers or []:
        m_name = ""
        m_prof = db.get(MasterProfile, off.master_id)
        if m_prof:
            u = db.get(User, m_prof.user_id)
            m_name = u.full_name if u else ""
        offers.append(
            OfferOut(
                id=off.id,
                master_id=off.master_id,
                master_name=m_name,
                master_full_name=m_name,
                status=off.status.value if hasattr(off.status, "value") else str(off.status),
                expires_at=off.expires_at,
            )
        )

    # Quotes
    quotes = [
        QuoteOut.model_validate(q)
        for q in sorted(order.quotes or [], key=lambda x: x.id)
    ]

    # Payment
    pmt = db.scalar(select(Payment).where(Payment.order_id == order.id))
    pmt_out = (
        AdminPaymentOut(
            id=pmt.id,
            order_id=pmt.order_id,
            method=pmt.method,
            amount=pmt.amount,
            status=pmt.status,
            created_at=pmt.created_at,
        )
        if pmt
        else None
    )

    # Review
    rev = db.scalar(select(Review).where(Review.order_id == order.id))
    rev_out = (
        AdminReviewOut(
            id=rev.id,
            order_id=rev.order_id,
            rating=rev.rating,
            comment=rev.comment,
            created_at=rev.created_at,
        )
        if rev
        else None
    )

    cust_name = order.customer.full_name if order.customer else ""
    cust_phone = order.customer.phone if order.customer else ""
    cat_name = order.category.name if order.category else ""

    return AdminOrderDetailOut(
        id=order.id,
        status=order.status,
        category_id=order.category_id,
        category=cat_name,
        category_name=cat_name,
        customer_id=order.customer_id,
        customer_name=cust_name,
        customer_phone=cust_phone,
        master_id=order.master_id,
        master_name=master_name,
        city=order.city,
        district=order.district,
        address=order.address,
        description=order.description,
        selection_mode=order.selection_mode,
        agreed_price=order.agreed_price,
        commission_rate=order.commission_rate,
        commission_amount=order.commission_amount,
        created_at=order.created_at,
        history=order.history,
        offers=offers,
        quotes=quotes,
        payment=pmt_out,
        review=rev_out,
    )


# ==================== Kategoriya amallari ====================


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(data: CategoryCreate, db: Session = Depends(get_db)):
    slug = data.slug or slugify(data.name)
    if not slug:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Nomdan slug yasab bo'lmadi, slug ni qo'lda kiriting",
        )
    if db.scalar(select(Category.id).where(Category.slug == slug)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, SLUG_TAKEN)

    category = Category(name=data.name, slug=slug)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, SLUG_TAKEN)
    db.refresh(category)
    return category


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, data: CategoryUpdate, db: Session = Depends(get_db)):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kategoriya topilmadi")
    if data.name is not None:
        category.name = data.name
    if data.is_active is not None:
        category.is_active = data.is_active
    db.commit()
    db.refresh(category)
    return category


# ==================== Usta amallari ====================


@router.patch("/masters/{profile_id}/approval", response_model=ApprovalOut)
def set_master_approval(profile_id: int, data: ApprovalIn, db: Session = Depends(get_db)):
    profile = db.get(MasterProfile, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usta topilmadi")
    profile.is_approved = data.is_approved
    db.commit()
    db.refresh(profile)
    return profile


# ==================== Buyurtma amallari ====================


@router.get("/orders", response_model=list[AdminOrderListItem])
def list_admin_orders(
    status: OrderStatus | None = None,
    category_id: int | None = None,
    city: str | None = None,
    master_id: int | None = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)

    stmt = (
        select(Order)
        .options(
            selectinload(Order.category),
            selectinload(Order.customer),
            selectinload(Order.master).selectinload(MasterProfile.user),
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
    )
    if status is not None:
        stmt = stmt.where(Order.status == status)
    if category_id is not None:
        stmt = stmt.where(Order.category_id == category_id)
    if city and city.strip():
        stmt = stmt.where(func.lower(Order.city) == city.strip().lower())
    if master_id is not None:
        stmt = stmt.where(Order.master_id == master_id)

    orders = db.scalars(stmt.offset(offset).limit(limit)).all()
    items = []
    for o in orders:
        cat_name = o.category.name if o.category else ""
        cust_name = o.customer.full_name if o.customer else ""
        cust_phone = o.customer.phone if o.customer else ""
        m_name = (
            o.master.user.full_name
            if o.master and o.master.user
            else None
        )
        items.append(
            AdminOrderListItem(
                id=o.id,
                status=o.status,
                category=cat_name,
                category_name=cat_name,
                category_id=o.category_id,
                customer_id=o.customer_id,
                customer_name=cust_name,
                customer_phone=cust_phone,
                master_id=o.master_id,
                master_name=m_name,
                city=o.city,
                district=o.district,
                agreed_price=o.agreed_price,
                commission_amount=o.commission_amount,
                created_at=o.created_at,
            )
        )
    return items


@router.get("/orders/{order_id}", response_model=AdminOrderDetailOut)
def get_admin_order(order_id: int, db: Session = Depends(get_db)):
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.category),
            selectinload(Order.customer),
            selectinload(Order.master).selectinload(MasterProfile.user),
            selectinload(Order.history),
            selectinload(Order.offers),
            selectinload(Order.quotes),
        )
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")
    return _admin_order_detail_out(order, db)


@router.patch("/orders/{order_id}/assign", response_model=AdminOrderDetailOut)
def admin_assign_order(
    order_id: int,
    data: AdminAssignIn,
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    order = admin_ops.admin_assign_master(
        db=db,
        order_id=order_id,
        master_profile_id=data.master_id,
        admin=admin,
    )
    db.commit()
    db.refresh(order)
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.category),
            selectinload(Order.customer),
            selectinload(Order.master).selectinload(MasterProfile.user),
            selectinload(Order.history),
            selectinload(Order.offers),
            selectinload(Order.quotes),
        )
    )
    return _admin_order_detail_out(order, db)


# ==================== Foydalanuvchi amallari ====================


@router.get("/users", response_model=list[AdminUserItem])
def list_admin_users(
    role: Role | None = None,
    is_active: bool | None = None,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)

    stmt = (
        select(User, MasterProfile)
        .outerjoin(MasterProfile, User.id == MasterProfile.user_id)
        .order_by(User.id.desc())
    )
    if role is not None:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.phone).like(term),
                func.lower(User.full_name).like(term),
            )
        )

    rows = db.execute(stmt.offset(offset).limit(limit)).all()
    items = []
    for user, profile in rows:
        items.append(
            AdminUserItem(
                id=user.id,
                phone=user.phone,
                full_name=user.full_name,
                role=user.role,
                is_active=user.is_active,
                created_at=user.created_at,
                profile_id=profile.id if profile else None,
                is_approved=profile.is_approved if profile else None,
                is_available=profile.is_available if profile else None,
                rating_avg=profile.rating_avg if profile else None,
                rating_count=profile.rating_count if profile else None,
            )
        )
    return items


@router.patch("/users/{user_id}/status", response_model=AdminUserItem)
def update_user_status(
    user_id: int,
    data: UserStatusIn,
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    user = admin_ops.set_user_active(
        db=db,
        target_user_id=user_id,
        is_active=data.is_active,
        admin=admin,
    )
    db.commit()
    db.refresh(user)

    profile = db.scalar(select(MasterProfile).where(MasterProfile.user_id == user.id))
    return AdminUserItem(
        id=user.id,
        phone=user.phone,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        profile_id=profile.id if profile else None,
        is_approved=profile.is_approved if profile else None,
        is_available=profile.is_available if profile else None,
        rating_avg=profile.rating_avg if profile else None,
        rating_count=profile.rating_count if profile else None,
    )


# ==================== Komissiyalar hisoboti ====================


@router.get("/commissions", response_model=CommissionsReportOut)
def get_commissions_report(
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    report = admin_ops.commissions_report(
        db=db,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    items = [
        CommissionOrderItem(
            id=item["id"],
            completed_at=item["completed_at"],
            category_name=item["category_name"],
            master_name=item["master_name"],
            agreed_price=item["agreed_price"],
            commission_rate=item["commission_rate"],
            commission_amount=item["commission_amount"],
            master_net=item["master_net"],
            payment_amount=item.get("payment_amount"),
            payment_status=item.get("payment_status"),
        )
        for item in report.orders
    ]
    return CommissionsReportOut(
        total_completed_orders=report.total_completed_orders,
        total_orders=report.total_orders,
        total=report.total,
        gross_total=report.gross_total,
        commission_total=report.commission_total,
        orders=items,
    )
