"""order_flow uchun unit testlar: HTTP yo'q, faqat db fixture."""

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app import models
from app.models.enums import OrderStatus, Role, SelectionMode
from app.services import order_flow
from app.services.order_flow import ADMIN_TRANSITIONS, MASTER_TRANSITIONS, TRANSITIONS, transition

S = OrderStatus


# ---------- yordamchilar ----------

@pytest.fixture
def mk_user(db):
    counter = iter(range(1000, 9999))

    def _mk(role: Role) -> models.User:
        u = models.User(
            phone=f"+998900{next(counter):06d}",
            password_hash="x",  # bu testlarda parol tekshirilmaydi
            full_name=f"{role.value} user",
            role=role,
        )
        db.add(u)
        db.flush()
        if role == Role.MASTER:
            db.add(models.MasterProfile(user_id=u.id, city="Toshkent", district="Chilonzor",
                                        is_approved=True))
            db.flush()
            db.refresh(u)
        return u

    return _mk


@pytest.fixture
def category(db):
    c = models.Category(name="Santexnik", slug="santexnik")
    db.add(c)
    db.flush()
    return c


@pytest.fixture
def customer(mk_user):
    return mk_user(Role.CUSTOMER)


@pytest.fixture
def admin(mk_user):
    return mk_user(Role.ADMIN)


@pytest.fixture
def master(mk_user):
    return mk_user(Role.MASTER)


@pytest.fixture
def mk_order(db, category, customer):
    def _mk(status: OrderStatus = S.SEARCHING, owner=None, master=None) -> models.Order:
        o = models.Order(
            customer_id=(owner or customer).id,
            category_id=category.id,
            master_id=master.master_profile.id if master else None,
            description="Kran oqyapti",
            city="Toshkent",
            district="Chilonzor",
            address="1-uy",
            selection_mode=SelectionMode.MANUAL,
            status=status,  # test sozlamasi: holatni to'g'ridan-to'g'ri qo'yamiz
        )
        db.add(o)
        db.flush()
        return o

    return _mk


def history_count(db, order) -> int:
    db.flush()
    return db.scalar(
        select(func.count()).select_from(models.OrderStatusHistory)
        .where(models.OrderStatusHistory.order_id == order.id)
    )


def expect(code: int, fn, *args):
    with pytest.raises(HTTPException) as exc:
        fn(*args)
    assert exc.value.status_code == code
    return exc.value


# ---------- jadvalning o'zi ----------

def test_transition_table_shape():
    assert TRANSITIONS[S.SEARCHING] == {S.ASSIGNED, S.CANCELLED}
    assert TRANSITIONS[S.ASSIGNED] == {S.IN_PROGRESS, S.CANCELLED, S.SEARCHING}
    assert TRANSITIONS[S.IN_PROGRESS] == {S.COMPLETED, S.CANCELLED}
    assert TRANSITIONS[S.COMPLETED] == set()
    assert TRANSITIONS[S.CANCELLED] == set()
    assert order_flow.TERMINAL == {S.COMPLETED, S.CANCELLED}


def test_every_table_transition_has_a_permitted_actor():
    all_pairs = {(f, t) for f, nxt in TRANSITIONS.items() for t in nxt}
    customer_pairs = {(S.SEARCHING, S.CANCELLED), (S.ASSIGNED, S.CANCELLED)}
    assert all_pairs == MASTER_TRANSITIONS | ADMIN_TRANSITIONS | customer_pairs
    # Rol jadvallari holatlar jadvalidan tashqariga chiqmaydi
    assert MASTER_TRANSITIONS <= all_pairs and ADMIN_TRANSITIONS <= all_pairs


# ---------- har bir ruxsat etilgan o'tish ----------

def _allowed_cases():
    cases = [("customer", S.SEARCHING, S.CANCELLED), ("customer", S.ASSIGNED, S.CANCELLED)]
    cases += [("master", f, t) for f, t in sorted(MASTER_TRANSITIONS)]
    cases += [("admin", f, t) for f, t in sorted(ADMIN_TRANSITIONS)]
    return cases


@pytest.mark.parametrize("who,from_s,to_s", _allowed_cases())
def test_allowed_transition_writes_one_history_row(db, mk_order, customer, master, admin,
                                                    who, from_s, to_s):
    actor = {"customer": customer, "master": master, "admin": admin}[who]
    order = mk_order(from_s, master=master)
    entry = transition(db, order, to_s, actor)

    assert order.status == to_s
    assert history_count(db, order) == 1
    row = db.scalars(select(models.OrderStatusHistory)
                     .where(models.OrderStatusHistory.order_id == order.id)).one()
    assert row is entry
    assert (row.from_status, row.to_status, row.changed_by) == (from_s, to_s, actor.id)


def test_transition_accepts_string_status(db, mk_order, customer):
    order = mk_order()
    transition(db, order, "cancelled", customer)
    assert order.status == S.CANCELLED


def test_transition_does_not_commit(db, mk_order, customer):
    order = mk_order()
    db.commit()
    transition(db, order, S.CANCELLED, customer)
    db.rollback()
    db.refresh(order)
    assert order.status == S.SEARCHING
    assert history_count(db, order) == 0


# ---------- noqonuniy o'tishlar: 409 ----------

@pytest.mark.parametrize("from_s,to_s", [
    (S.COMPLETED, S.SEARCHING),
    (S.CANCELLED, S.ASSIGNED),
    (S.SEARCHING, S.IN_PROGRESS),
    (S.SEARCHING, S.COMPLETED),
    (S.IN_PROGRESS, S.SEARCHING),
    (S.IN_PROGRESS, S.ASSIGNED),
    (S.ASSIGNED, S.COMPLETED),
])
def test_illegal_transitions_409(db, mk_order, admin, master, from_s, to_s):
    order = mk_order(from_s, master=master)
    for actor in (admin, master):  # aktor qanday bo'lmasin, jadval birinchi
        err = expect(409, transition, db, order, to_s, actor)
        assert err.detail == "Bu holatdan o'tish mumkin emas"
    assert order.status == from_s
    assert history_count(db, order) == 0


@pytest.mark.parametrize("terminal", [S.COMPLETED, S.CANCELLED])
def test_terminal_orders_never_change(db, mk_order, customer, master, admin, terminal):
    order = mk_order(terminal, master=master)
    for to_s in S:
        for actor in (customer, master, admin):
            expect(409, transition, db, order, to_s, actor)
    assert order.status == terminal
    assert history_count(db, order) == 0


@pytest.mark.parametrize("st", list(S))
def test_same_status_is_409(db, mk_order, admin, st):
    order = mk_order(st)
    expect(409, transition, db, order, st, admin)


def test_unknown_status_is_409(db, mk_order, admin):
    expect(409, transition, db, mk_order(), "deleted", admin)


# ---------- aktor qoidalari: 403 ----------

def test_customer_cannot_cancel_in_progress(db, mk_order, customer, master):
    order = mk_order(S.IN_PROGRESS, master=master)
    err = expect(403, transition, db, order, S.CANCELLED, customer)
    assert err.detail == "Bu amal uchun ruxsat yo'q"
    assert order.status == S.IN_PROGRESS
    assert history_count(db, order) == 0


def test_customer_cannot_cancel_someone_elses_order(db, mk_order, mk_user):
    other = mk_user(Role.CUSTOMER)
    for st in (S.SEARCHING, S.ASSIGNED):
        order = mk_order(st)
        expect(403, transition, db, order, S.CANCELLED, other)
        assert order.status == st


@pytest.mark.parametrize("from_s,to_s", [
    (S.SEARCHING, S.ASSIGNED),
    (S.ASSIGNED, S.SEARCHING),
    (S.ASSIGNED, S.IN_PROGRESS),
    (S.IN_PROGRESS, S.COMPLETED),
])
def test_customer_cannot_trigger_other_transitions(db, mk_order, customer, master, from_s, to_s):
    order = mk_order(from_s, master=master)
    expect(403, transition, db, order, to_s, customer)


def test_admin_can_cancel_in_progress(db, mk_order, admin, master):
    order = mk_order(S.IN_PROGRESS, master=master)
    transition(db, order, S.CANCELLED, admin)
    assert order.status == S.CANCELLED
    assert order.history[-1].changed_by == admin.id


@pytest.mark.parametrize("from_s,to_s", [
    (S.ASSIGNED, S.IN_PROGRESS),
    (S.IN_PROGRESS, S.COMPLETED),
])
def test_admin_cannot_start_or_complete(db, mk_order, admin, master, from_s, to_s):
    expect(403, transition, db, mk_order(from_s, master=master), to_s, admin)


def test_master_only_on_own_order(db, mk_order, master, mk_user):
    other_master = mk_user(Role.MASTER)
    order = mk_order(S.ASSIGNED, master=master)
    expect(403, transition, db, order, S.IN_PROGRESS, other_master)
    order_ip = mk_order(S.IN_PROGRESS, master=master)
    expect(403, transition, db, order_ip, S.COMPLETED, other_master)
    # Biriktirilmagan buyurtmani qabul qilib bo'lmaydi
    expect(403, transition, db, mk_order(S.SEARCHING), S.ASSIGNED, master)


@pytest.mark.parametrize("from_s,to_s", [
    (S.ASSIGNED, S.IN_PROGRESS),
    (S.IN_PROGRESS, S.COMPLETED),
    (S.SEARCHING, S.CANCELLED),
])
def test_anonymous_actor_forbidden(db, mk_order, master, from_s, to_s):
    order = mk_order(from_s, master=master)
    expect(403, transition, db, order, to_s, None)


@pytest.mark.parametrize("from_s", [S.SEARCHING, S.ASSIGNED, S.IN_PROGRESS])
def test_master_cannot_cancel(db, mk_order, master, from_s):
    expect(403, transition, db, mk_order(from_s, master=master), S.CANCELLED, master)


def test_master_without_profile_forbidden(db, mk_order, master):
    bare = models.User(phone="+998909999999", password_hash="x", full_name="B", role=Role.MASTER)
    db.add(bare)
    db.flush()
    expect(403, transition, db, mk_order(S.ASSIGNED, master=master), S.IN_PROGRESS, bare)


# ---------- tarix ----------

def test_create_order_history(db, mk_order, customer):
    order = mk_order()
    entry = order_flow.create_order_history(db, order, customer)
    db.flush()
    assert order.status == S.SEARCHING
    assert (entry.from_status, entry.to_status, entry.changed_by) == (None, S.SEARCHING, customer.id)
    assert history_count(db, order) == 1


def test_full_lifecycle_history_records_actors(db, mk_order, customer, master, admin):
    order = mk_order()
    order_flow.create_order_history(db, order, customer)
    order.master_id = master.master_profile.id  # biriktirishni chaqiruvchi qiladi
    transition(db, order, S.ASSIGNED, admin)
    transition(db, order, S.SEARCHING, master)
    transition(db, order, S.ASSIGNED, master)
    transition(db, order, S.IN_PROGRESS, master)
    transition(db, order, S.COMPLETED, master)
    db.commit()
    db.refresh(order)

    steps = [(h.from_status, h.to_status, h.changed_by) for h in order.history]
    assert steps == [
        (None, S.SEARCHING, customer.id),
        (S.SEARCHING, S.ASSIGNED, admin.id),
        (S.ASSIGNED, S.SEARCHING, master.id),
        (S.SEARCHING, S.ASSIGNED, master.id),
        (S.ASSIGNED, S.IN_PROGRESS, master.id),
        (S.IN_PROGRESS, S.COMPLETED, master.id),
    ]
    expect(409, transition, db, order, S.CANCELLED, admin)
