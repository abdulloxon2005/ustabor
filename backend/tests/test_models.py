import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models import Category, MasterProfile, MasterService, Order, Review, User
from app.models.enums import OrderStatus, PricingType, Role, SelectionMode


def make_user(db, phone="+998901111111", role=Role.CUSTOMER):
    user = User(phone=phone, password_hash="x", full_name="Test", role=role)
    db.add(user)
    db.flush()
    return user


def make_category(db, slug="santexnik"):
    cat = Category(name="Santexnik", slug=slug)
    db.add(cat)
    db.flush()
    return cat


def make_master(db, phone="+998902222221"):
    user = make_user(db, phone, Role.MASTER)
    profile = MasterProfile(user_id=user.id, city="Toshkent", district="Chilonzor")
    db.add(profile)
    db.flush()
    return profile


def make_order(db, customer, category, master=None):
    order = Order(
        customer_id=customer.id,
        category_id=category.id,
        master_id=master.id if master else None,
        description="Kran oqyapti",
        city="Toshkent",
        district="Chilonzor",
        address="Chilonzor 5-kvartal",
        selection_mode=SelectionMode.MANUAL,
    )
    db.add(order)
    db.flush()
    return order


def test_phone_must_be_unique(db):
    make_user(db, "+998901111111")
    with pytest.raises(IntegrityError):
        make_user(db, "+998901111111")


def test_foreign_keys_are_enforced(db):
    # mavjud bo'lmagan customer_id va category_id
    order = Order(
        customer_id=999,
        category_id=999,
        description="x",
        city="Toshkent",
        district="Chilonzor",
        address="x",
        selection_mode=SelectionMode.MANUAL,
    )
    db.add(order)
    with pytest.raises(IntegrityError):
        db.flush()


def test_order_defaults(db):
    customer = make_user(db)
    order = make_order(db, customer, make_category(db))
    assert order.status == OrderStatus.SEARCHING
    assert order.commission_rate == settings.COMMISSION_RATE
    assert order.master_id is None
    assert order.agreed_price is None


def test_master_service_unique_per_category(db):
    master = make_master(db)
    cat = make_category(db)
    db.add(
        MasterService(
            master_id=master.id,
            category_id=cat.id,
            pricing_type=PricingType.FIXED,
            base_price=150_000,
        )
    )
    db.flush()
    db.add(
        MasterService(
            master_id=master.id,
            category_id=cat.id,
            pricing_type=PricingType.QUOTE,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()


def test_review_rating_must_be_1_to_5(db):
    customer = make_user(db)
    master = make_master(db)
    order = make_order(db, customer, make_category(db), master)
    db.add(
        Review(
            order_id=order.id,
            customer_id=customer.id,
            master_id=master.id,
            rating=6,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()


def test_one_review_per_order(db):
    customer = make_user(db)
    master = make_master(db)
    order = make_order(db, customer, make_category(db), master)
    db.add(Review(order_id=order.id, customer_id=customer.id, master_id=master.id, rating=5))
    db.flush()
    db.add(Review(order_id=order.id, customer_id=customer.id, master_id=master.id, rating=4))
    with pytest.raises(IntegrityError):
        db.flush()