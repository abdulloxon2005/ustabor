from datetime import datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, MasterProfile, MasterService, Order, OrderOffer, User
from app.models.enums import OfferStatus, OrderStatus
from app.schemas.mobile import AnalyticsFilter


def filtered_orders(db: Session, filters: AnalyticsFilter):
    stmt = select(Order)
    if filters.start_date:
        start = datetime.combine(filters.start_date, time.min, tzinfo=timezone.utc)
        stmt = stmt.where(Order.created_at >= start)
    if filters.end_date:
        end = datetime.combine(filters.end_date, time.max, tzinfo=timezone.utc)
        stmt = stmt.where(Order.created_at <= end)
    if filters.category_id:
        stmt = stmt.where(Order.category_id == filters.category_id)
    if filters.master_id:
        stmt = stmt.where(Order.master_id == filters.master_id)
    if filters.region and filters.region.strip():
        region = f"%{filters.region.strip().lower()}%"
        stmt = stmt.where(
            func.lower(Order.city).like(region) | func.lower(Order.district).like(region)
        )
    return stmt


def order_summary(db: Session, filters: AnalyticsFilter) -> dict:
    base = filtered_orders(db, filters).subquery()
    total = db.scalar(select(func.count()).select_from(base)) or 0
    statuses = db.execute(select(base.c.status, func.count()).group_by(base.c.status)).all()
    completed = sum(n for status, n in statuses if status == OrderStatus.COMPLETED)
    cancelled = sum(n for status, n in statuses if status == OrderStatus.CANCELLED)
    commission = db.scalar(select(func.coalesce(func.sum(base.c.commission_amount), 0))) or 0
    daily_rows = db.execute(
        select(func.date(base.c.created_at), func.count())
        .group_by(func.date(base.c.created_at)).order_by(func.date(base.c.created_at).desc())
        .limit(filters.limit).offset(filters.offset)
    ).all()
    return {
        "total_orders": total,
        "completed_orders": completed,
        "cancelled_orders": cancelled,
        "completion_rate_percent": round(completed * 100 / total, 2) if total else 0.0,
        "commission_total": commission,
        "status_counts": {getattr(s, "value", s): n for s, n in statuses},
        "daily_orders": [{"date": str(day), "orders_count": n} for day, n in daily_rows],
    }


def masters_report(db: Session, filters: AnalyticsFilter) -> list[dict]:
    filtered = filtered_orders(db, filters).subquery()
    completed = (
        select(filtered.c.master_id.label("master_id"), func.count(filtered.c.id).label("completed"),
               func.coalesce(func.sum(filtered.c.agreed_price), 0).label("gross"))
        .where(filtered.c.status == OrderStatus.COMPLETED, filtered.c.master_id.is_not(None))
        .group_by(filtered.c.master_id).subquery()
    )
    rejected_order_ids = select(filtered.c.id)
    rejected = (
        select(OrderOffer.master_id.label("master_id"), func.count(OrderOffer.id).label("rejected"))
        .where(OrderOffer.status == OfferStatus.REJECTED, OrderOffer.order_id.in_(rejected_order_ids))
        .group_by(OrderOffer.master_id).subquery()
    )
    stmt = (
        select(MasterProfile, User, completed.c.completed, completed.c.gross, rejected.c.rejected)
        .join(User, User.id == MasterProfile.user_id)
        .outerjoin(completed, completed.c.master_id == MasterProfile.id)
        .outerjoin(rejected, rejected.c.master_id == MasterProfile.id)
        .order_by(func.coalesce(completed.c.completed, 0).desc(), MasterProfile.rating_avg.desc())
    )
    if filters.master_id:
        stmt = stmt.where(MasterProfile.id == filters.master_id)
    if filters.region:
        region = f"%{filters.region.strip().lower()}%"
        stmt = stmt.where(func.lower(MasterProfile.city).like(region) | func.lower(MasterProfile.district).like(region))
    rows = db.execute(stmt.limit(filters.limit).offset(filters.offset)).all()
    result = []
    for profile, user, done, gross, rej in rows:
        services = db.scalars(select(Category.name).join(MasterService).where(MasterService.master_id == profile.id)).all()
        result.append({
            "id": profile.id, "user_id": user.id, "full_name": user.full_name,
            "phone": user.phone, "city": profile.city, "district": profile.district,
            "is_approved": profile.is_approved, "is_available": profile.is_available,
            "rating_avg": profile.rating_avg, "rating_count": profile.rating_count,
            "services": services, "completed_orders": done or 0,
            "rejected_offers": rej or 0, "gross_earnings": gross or 0,
        })
    return result


def category_report(db: Session, filters: AnalyticsFilter) -> list[dict]:
    base = filtered_orders(db, filters).subquery()
    rows = db.execute(
        select(Category.id, Category.name, func.count(base.c.id).label("orders_count"))
        .join(base, base.c.category_id == Category.id)
        .group_by(Category.id, Category.name)
        .order_by(func.count(base.c.id).desc(), Category.name)
        .limit(filters.limit).offset(filters.offset)
    ).all()
    return [{"category_id": cid, "category_name": name, "orders_count": count} for cid, name, count in rows]


def geo_report(db: Session, filters: AnalyticsFilter) -> dict:
    base = filtered_orders(db, filters).subquery()
    regions = db.execute(
        select(base.c.city, base.c.district, func.count(base.c.id))
        .group_by(base.c.city, base.c.district)
        .order_by(func.count(base.c.id).desc())
        .limit(filters.limit).offset(filters.offset)
    ).all()
    points = db.execute(
        select(base.c.id, base.c.latitude, base.c.longitude, base.c.city, base.c.district)
        .where(base.c.latitude.is_not(None), base.c.longitude.is_not(None))
        .order_by(base.c.id.desc()).limit(filters.limit).offset(filters.offset)
    ).all()
    return {
        "regions": [{"city": city, "district": district, "orders_count": count} for city, district, count in regions],
        "points": [{"order_id": oid, "latitude": lat, "longitude": lon, "city": city, "district": district} for oid, lat, lon, city, district in points],
    }


def revenue_report(db: Session, filters: AnalyticsFilter) -> dict:
    base = filtered_orders(db, filters).subquery()
    rows = db.execute(
        select(base.c.master_id, func.coalesce(func.sum(base.c.agreed_price), 0),
               func.coalesce(func.sum(base.c.commission_amount), 0), func.count(base.c.id))
        .where(base.c.status == OrderStatus.COMPLETED)
        .group_by(base.c.master_id)
        .order_by(func.sum(base.c.commission_amount).desc())
        .limit(filters.limit).offset(filters.offset)
    ).all()
    gross = db.scalar(select(func.coalesce(func.sum(base.c.agreed_price), 0)).where(base.c.status == OrderStatus.COMPLETED)) or 0
    commission = db.scalar(select(func.coalesce(func.sum(base.c.commission_amount), 0)).where(base.c.status == OrderStatus.COMPLETED)) or 0
    return {"gross_total": gross, "commission_total": commission, "by_master": [
        {"master_id": mid, "gross_total": total, "commission_total": fee, "completed_orders": count}
        for mid, total, fee, count in rows
    ]}


def rejection_report(db: Session, filters: AnalyticsFilter) -> list[dict]:
    order_ids = select(filtered_orders(db, filters).subquery().c.id)
    rows = db.execute(
        select(OrderOffer.master_id, User.full_name, func.count(OrderOffer.id))
        .join(MasterProfile, MasterProfile.id == OrderOffer.master_id)
        .join(User, User.id == MasterProfile.user_id)
        .where(OrderOffer.status == OfferStatus.REJECTED, OrderOffer.order_id.in_(order_ids))
        .group_by(OrderOffer.master_id, User.full_name)
        .order_by(func.count(OrderOffer.id).desc())
        .limit(filters.limit).offset(filters.offset)
    ).all()
    return [{"master_id": mid, "master_name": name, "rejected_offers": count} for mid, name, count in rows]
