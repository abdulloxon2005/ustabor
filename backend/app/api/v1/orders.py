from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_role
from app.core.config import settings
from app.db.session import get_db
from app.models import Category, Order, OrderStatusHistory, User
from app.models.enums import OrderStatus, Role, SelectionMode
from app.schemas.order import OrderCreate, OrderListItem, OrderOut
from app.services.order_flow import create_order_history, transition

router = APIRouter(prefix="/orders", tags=["orders"])


def _own_order(order_id: int, user: User, db: Session) -> Order:
    """Foydalanuvchining O'Z buyurtmasini qaytaradi; yo'q yoki begona -> 404."""
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id, Order.customer_id == user.id)
        .options(
            selectinload(Order.history),
            selectinload(Order.category),
        )
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buyurtma topilmadi")
    return order


def _order_out(order: Order) -> OrderOut:
    return OrderOut(
        id=order.id,
        customer_id=order.customer_id,
        category_id=order.category_id,
        category_name=order.category.name,
        master_id=order.master_id,
        description=order.description,
        city=order.city,
        district=order.district,
        address=order.address,
        status=order.status,
        selection_mode=order.selection_mode,
        agreed_price=order.agreed_price,
        commission_rate=order.commission_rate,
        commission_amount=order.commission_amount,
        created_at=order.created_at,
        history=order.history,
    )


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    data: OrderCreate,
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    cat = db.get(Category, data.category_id)
    if cat is None or not cat.is_active:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Kategoriya topilmadi yoki faol emas",
        )

    order = Order(
        customer_id=user.id,
        category_id=data.category_id,
        description=data.description,
        city=data.city,
        district=data.district,
        address=data.address,
        selection_mode=SelectionMode(data.selection_mode),
        master_id=None,
        agreed_price=None,
        commission_rate=settings.COMMISSION_RATE,
        commission_amount=None,
    )
    db.add(order)
    db.flush()
    create_order_history(db, order, user)
    db.commit()
    db.refresh(order)
    return _order_out(_own_order(order.id, user, db))


@router.get("", response_model=list[OrderListItem])
def list_orders(
    status_filter: OrderStatus | None = None,
    limit: int = 20,
    offset: int = 0,
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)

    stmt = (
        select(Order)
        .where(Order.customer_id == user.id)
        .options(selectinload(Order.category))
        .order_by(Order.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter is not None:
        stmt = stmt.where(Order.status == status_filter)

    orders = db.scalars(stmt).all()
    return [
        OrderListItem(
            id=o.id,
            category_id=o.category_id,
            category_name=o.category.name,
            description=o.description,
            city=o.city,
            district=o.district,
            status=o.status,
            selection_mode=o.selection_mode,
            agreed_price=o.agreed_price,
            created_at=o.created_at,
        )
        for o in orders
    ]


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    return _order_out(_own_order(order_id, user, db))


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel_order(
    order_id: int,
    user: User = Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    order = _own_order(order_id, user, db)
    transition(db, order, OrderStatus.CANCELLED, user)
    db.commit()
    db.refresh(order)
    return _order_out(_own_order(order.id, user, db))
