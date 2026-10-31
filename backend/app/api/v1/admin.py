from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.core.config import MAX_DB_INT
from app.db.session import get_db
from app.models import (
    AdminAuditLog,
    Category,
    ChatReport,
    Dispute,
    MasterProfile,
    Order,
    OrderMessage,
    Payment,
    PlatformSetting,
    Review,
    User,
)
from app.models.enums import DisputeStatus, OrderStatus, Role
from app.schemas.admin import (
    AdminAnalyticsOut,
    AdminAssignIn,
    AdminAuditLogItem,
    AdminOrderDetailOut,
    AdminOrderListItem,
    AdminPaymentOut,
    AdminReviewOut,
    AdminUserItem,
    CommissionOrderItem,
    CommissionsReportOut,
    UserStatusIn,
)
from app.schemas.dispute import AdminDisputeListItem, AdminDisputeResolve, DisputeOut
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate, slugify
from app.schemas.master import ApprovalIn, ApprovalOut
from app.schemas.order import HistoryOut, OfferOut
from app.schemas.quote import QuoteOut
from app.schemas.mobile import (
    AdminMasterItem, AdminMasterStats, AnalyticsFilter, ChatMessageModerationIn,
    ChatReportOut, CommissionSettingsIn, CommissionSettingsOut,
    MasterLocationOut,
)
from app.services import admin_ops, notify
from app.services import admin_analytics
from app.services.order_flow import transition

# Router darajasida: admindan boshqa hech kim kira olmaydi
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)

SLUG_TAKEN = "Bu slug allaqachon mavjud"


def _clamp_pagination(limit: int, offset: int) -> tuple[int, int]:
    return min(max(limit, 1), 100), min(max(offset, 0), MAX_DB_INT)


def _analytics_filter(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    category_id: int | None = Query(default=None, gt=0, le=MAX_DB_INT),
    master_id: int | None = Query(default=None, gt=0, le=MAX_DB_INT),
    region: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=MAX_DB_INT),
) -> AnalyticsFilter:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "start_date end_date dan keyin bo'lishi mumkin emas")
    return AnalyticsFilter(start_date=start_date, end_date=end_date,
                           category_id=category_id, master_id=master_id,
                           region=region, limit=limit, offset=offset)


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
def create_category(
    data: CategoryCreate,
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
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
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, SLUG_TAKEN)
    admin_ops.log_admin_action(db, admin, "create_category", "category", category.id, data.name)
    db.commit()
    db.refresh(category)
    return category


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    data: CategoryUpdate,
    category_id: int = Path(..., le=MAX_DB_INT),
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kategoriya topilmadi")
    if data.name is not None:
        category.name = data.name
    if data.is_active is not None:
        category.is_active = data.is_active
    admin_ops.log_admin_action(db, admin, "update_category", "category", category.id)
    db.commit()
    db.refresh(category)
    return category


# ==================== Usta amallari ====================


@router.patch("/masters/{profile_id}/approval", response_model=ApprovalOut)
def set_master_approval(
    data: ApprovalIn,
    profile_id: int = Path(..., le=MAX_DB_INT),
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    profile = db.get(MasterProfile, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usta topilmadi")
    profile.is_approved = data.is_approved
    admin_ops.log_admin_action(
        db, admin, "approve_master" if data.is_approved else "revoke_master_approval",
        "master_profile", profile_id,
    )
    if data.is_approved:
        notify.notify_user(
            db,
            profile.user_id,
            "master_approved",
            "Profilingiz tasdiqlandi",
            "Endi mijozlarga ko'rinasiz va buyurtmalar qabul qila olasiz",
        )
    db.commit()
    db.refresh(profile)
    return profile


# ==================== Buyurtma amallari ====================


@router.get("/orders", response_model=list[AdminOrderListItem])
def list_admin_orders(
    status: OrderStatus | None = None,
    category_id: int | None = Query(default=None, le=MAX_DB_INT),
    city: str | None = None,
    master_id: int | None = Query(default=None, le=MAX_DB_INT),
    limit: int = 20,
    offset: int = Query(default=0, le=MAX_DB_INT),
    db: Session = Depends(get_db),
):
    limit, offset = _clamp_pagination(limit, offset)

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
def get_admin_order(
    order_id: int = Path(..., le=MAX_DB_INT),
    db: Session = Depends(get_db),
):
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
    data: AdminAssignIn,
    order_id: int = Path(..., le=MAX_DB_INT),
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


@router.post("/orders/{order_id}/cancel", response_model=AdminOrderDetailOut)
def admin_cancel_order(
    order_id: int = Path(..., le=MAX_DB_INT),
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")
    transition(db, order, OrderStatus.CANCELLED, actor=admin)
    admin_ops.log_admin_action(db, admin, "cancel_order", "order", order_id)
    db.commit()
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
    offset: int = Query(default=0, le=MAX_DB_INT),
    db: Session = Depends(get_db),
):
    limit, offset = _clamp_pagination(limit, offset)

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
    data: UserStatusIn,
    user_id: int = Path(..., le=MAX_DB_INT),
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
    offset: int = Query(default=0, le=MAX_DB_INT),
    db: Session = Depends(get_db),
):
    limit, offset = _clamp_pagination(limit, offset)
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


# ==================== Shikoyatlar ====================


@router.get("/disputes", response_model=list[AdminDisputeListItem])
def list_disputes(
    status_filter: DisputeStatus | None = Query(default=None, alias="status"),
    limit: int = 20,
    offset: int = Query(default=0, le=MAX_DB_INT),
    db: Session = Depends(get_db),
):
    limit, offset = _clamp_pagination(limit, offset)

    stmt = (
        select(Dispute, User.full_name, User.role, Order.status, Category.name)
        .join(User, Dispute.raised_by == User.id)
        .join(Order, Dispute.order_id == Order.id)
        .join(Category, Order.category_id == Category.id)
        .order_by(Dispute.created_at.desc(), Dispute.id.desc())
    )
    if status_filter is not None:
        stmt = stmt.where(Dispute.status == status_filter)

    rows = db.execute(stmt.offset(offset).limit(limit)).all()
    return [
        AdminDisputeListItem(
            id=d.id,
            order_id=d.order_id,
            status=d.status,
            reason=d.reason,
            admin_note=d.admin_note,
            raised_by_name=full_name,
            raised_by_role=role.value if hasattr(role, "value") else str(role),
            category_name=cat_name,
            order_status=order_status.value if hasattr(order_status, "value") else str(order_status),
            created_at=d.created_at,
            resolved_at=d.resolved_at,
        )
        for d, full_name, role, order_status, cat_name in rows
    ]


@router.patch("/disputes/{dispute_id}", response_model=DisputeOut)
def resolve_dispute(
    data: AdminDisputeResolve,
    dispute_id: int = Path(..., le=MAX_DB_INT),
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    dispute = db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shikoyat topilmadi")
    if dispute.status != DisputeStatus.OPEN:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu shikoyat allaqachon hal qilingan")

    dispute.status = DisputeStatus(data.status)
    dispute.admin_note = data.admin_note
    dispute.resolved_at = datetime.now(timezone.utc)
    admin_ops.log_admin_action(
        db, admin, "resolve_dispute", "dispute", dispute_id, data.status
    )
    db.commit()
    db.refresh(dispute)
    return dispute


# ==================== Audit log ====================


@router.get("/audit-log", response_model=list[AdminAuditLogItem])
def list_audit_log(
    admin_id: int | None = Query(default=None, le=MAX_DB_INT),
    action: str | None = Query(default=None, max_length=60),
    limit: int = 20,
    offset: int = Query(default=0, le=MAX_DB_INT),
    db: Session = Depends(get_db),
):
    limit, offset = _clamp_pagination(limit, offset)

    stmt = (
        select(AdminAuditLog, User.full_name)
        .join(User, AdminAuditLog.admin_id == User.id)
        .order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
    )
    if admin_id is not None:
        stmt = stmt.where(AdminAuditLog.admin_id == admin_id)
    if action is not None:
        stmt = stmt.where(AdminAuditLog.action == action)

    rows = db.execute(stmt.offset(offset).limit(limit)).all()
    return [
        AdminAuditLogItem(
            id=entry.id,
            admin_id=entry.admin_id,
            admin_name=admin_name,
            action=entry.action,
            target_type=entry.target_type,
            target_id=entry.target_id,
            detail=entry.detail,
            created_at=entry.created_at,
        )
        for entry, admin_name in rows
    ]


# ==================== Mobil tayyorgarligi va monitoring ====================


@router.get("/masters", response_model=list[AdminMasterItem])
def list_admin_masters(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=MAX_DB_INT),
    region: str | None = Query(default=None, max_length=80),
    db: Session = Depends(get_db),
):
    return admin_analytics.masters_report(
        db, AnalyticsFilter(limit=limit, offset=offset, region=region)
    )


@router.get("/masters/locations", response_model=list[MasterLocationOut])
def list_master_locations(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=MAX_DB_INT),
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(MasterProfile).join(User).where(
        MasterProfile.location_sharing_enabled.is_(True),
        MasterProfile.latitude.is_not(None), MasterProfile.longitude.is_not(None),
    ).order_by(MasterProfile.location_updated_at.desc()).offset(offset).limit(limit)).all()
    result = [MasterLocationOut(
        master_id=p.id, full_name=p.user.full_name, latitude=p.latitude,
        longitude=p.longitude, location_updated_at=p.location_updated_at,
        is_available=p.is_available,
    ) for p in rows]
    admin_ops.log_admin_action(db, admin, "view_master_locations", "master_profile", None, f"count={len(result)}")
    db.commit()
    return result


@router.get("/masters/{master_id}/statistics", response_model=AdminMasterStats)
def get_master_statistics(
    master_id: int = Path(..., le=MAX_DB_INT),
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    items = admin_analytics.masters_report(db, AnalyticsFilter(master_id=master_id, limit=1))
    if not items:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usta topilmadi")
    profile = db.get(MasterProfile, master_id)
    item = items[0]
    item["location_sharing_enabled"] = profile.location_sharing_enabled
    item["location_updated_at"] = profile.location_updated_at
    return item


@router.get("/masters/{master_id}/location", response_model=MasterLocationOut)
def get_master_location(
    master_id: int = Path(..., le=MAX_DB_INT),
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    profile = db.get(MasterProfile, master_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usta topilmadi")
    if not profile.location_sharing_enabled or profile.latitude is None or profile.longitude is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usta joylashuvini ulashmagan")
    admin_ops.log_admin_action(db, admin, "view_master_location", "master_profile", master_id)
    db.commit()
    return MasterLocationOut(
        master_id=profile.id, full_name=profile.user.full_name,
        latitude=profile.latitude, longitude=profile.longitude,
        location_updated_at=profile.location_updated_at,
        is_available=profile.is_available,
    )


@router.get("/settings/commission", response_model=CommissionSettingsOut)
def get_commission_settings(db: Session = Depends(get_db)):
    setting = db.get(PlatformSetting, 1)
    if setting is None:
        from app.core.config import settings
        return CommissionSettingsOut(enabled=True, rate=settings.COMMISSION_RATE)
    return CommissionSettingsOut(enabled=setting.commission_enabled,
                                  rate=setting.commission_rate, updated_at=setting.updated_at)


@router.patch("/settings/commission", response_model=CommissionSettingsOut)
def update_commission_settings(
    data: CommissionSettingsIn,
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    setting = db.get(PlatformSetting, 1)
    if setting is None:
        setting = PlatformSetting(id=1)
        db.add(setting)
    setting.commission_enabled = data.enabled
    setting.commission_rate = data.rate
    admin_ops.log_admin_action(db, admin, "update_commission_settings", "platform_settings", 1,
                               f"enabled={data.enabled};rate={data.rate}")
    db.commit()
    db.refresh(setting)
    return CommissionSettingsOut(enabled=setting.commission_enabled,
                                 rate=setting.commission_rate, updated_at=setting.updated_at)


def _admin_chat_messages(order_id: int, db: Session):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat topilmadi")
    rows = db.execute(select(OrderMessage, User.full_name).join(User, User.id == OrderMessage.sender_id)
                      .where(OrderMessage.order_id == order_id).order_by(OrderMessage.id)).all()
    return order, rows


@router.get("/chats")
def list_admin_chats(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=MAX_DB_INT),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(Order.id, Order.status, Order.created_at, func.count(OrderMessage.id))
                      .join(OrderMessage, OrderMessage.order_id == Order.id)
                      .group_by(Order.id).order_by(Order.id.desc()).offset(offset).limit(limit)).all()
    return [{"order_id": oid, "status": state, "created_at": created, "message_count": count}
            for oid, state, created, count in rows]


@router.get("/chats/reported", response_model=list[ChatReportOut])
def list_reported_chats(
    status_filter: str = Query(default="open", pattern="^(open|resolved|rejected)$", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=MAX_DB_INT),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(ChatReport, OrderMessage.body, User.full_name)
                      .join(OrderMessage, OrderMessage.id == ChatReport.message_id)
                      .join(User, User.id == ChatReport.reported_by)
                      .where(ChatReport.status == status_filter)
                      .order_by(ChatReport.created_at.desc()).offset(offset).limit(limit)).all()
    return [ChatReportOut.model_validate({**report.__dict__, "message_body": body,
                                          "reporter_name": name})
            for report, body, name in rows]


@router.get("/chats/{order_id}/messages")
def get_admin_chat_messages(
    order_id: int = Path(..., le=MAX_DB_INT),
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    order, rows = _admin_chat_messages(order_id, db)
    admin_ops.log_admin_action(db, admin, "view_chat", "order", order_id)
    db.commit()
    return [{"id": msg.id, "order_id": msg.order_id, "sender_id": msg.sender_id,
             "sender_name": name, "body": msg.body, "is_hidden": msg.is_hidden,
             "created_at": msg.created_at} for msg, name in rows]


@router.post("/chats/{order_id}/moderation")
def moderate_chat_message(
    data: ChatMessageModerationIn,
    order_id: int = Path(..., le=MAX_DB_INT),
    admin: User = Depends(require_role(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    msg = db.scalar(select(OrderMessage).where(OrderMessage.id == data.message_id,
                                               OrderMessage.order_id == order_id))
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xabar topilmadi")
    msg.is_hidden = data.hide
    for report in db.scalars(select(ChatReport).where(
        ChatReport.message_id == msg.id, ChatReport.status == "open"
    )):
        report.status = "resolved"
        report.admin_note = data.note
        report.reviewed_by = admin.id
        report.reviewed_at = datetime.now(timezone.utc)
    admin_ops.log_admin_action(db, admin, "moderate_chat_message", "order_message",
                               msg.id, f"hidden={data.hide};note={data.note or ''}")
    db.commit()
    return {"message_id": msg.id, "is_hidden": msg.is_hidden}


@router.get("/analytics/overview")
def analytics_overview(filters: AnalyticsFilter = Depends(_analytics_filter), db: Session = Depends(get_db)):
    return admin_analytics.order_summary(db, filters)


@router.get("/analytics/orders")
def analytics_orders(filters: AnalyticsFilter = Depends(_analytics_filter), db: Session = Depends(get_db)):
    return admin_analytics.order_summary(db, filters)


@router.get("/analytics/masters", response_model=list[AdminMasterItem])
def analytics_masters(filters: AnalyticsFilter = Depends(_analytics_filter), db: Session = Depends(get_db)):
    return admin_analytics.masters_report(db, filters)


@router.get("/analytics/revenue")
def analytics_revenue(filters: AnalyticsFilter = Depends(_analytics_filter), db: Session = Depends(get_db)):
    return admin_analytics.revenue_report(db, filters)


@router.get("/analytics/categories")
def analytics_categories(filters: AnalyticsFilter = Depends(_analytics_filter), db: Session = Depends(get_db)):
    return admin_analytics.category_report(db, filters)


@router.get("/analytics/geo")
def analytics_geo(filters: AnalyticsFilter = Depends(_analytics_filter), db: Session = Depends(get_db)):
    return admin_analytics.geo_report(db, filters)


@router.get("/analytics/rejections")
def analytics_rejections(filters: AnalyticsFilter = Depends(_analytics_filter), db: Session = Depends(get_db)):
    return admin_analytics.rejection_report(db, filters)


# ==================== Statistika ====================


@router.get("/analytics", response_model=AdminAnalyticsOut)
def get_analytics(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    return admin_ops.analytics(db=db, days=days)
