"""3. End-to-end (E2E) HTTP ssenariylar audit testlari."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.db.session import SessionLocal
from app.main import app
from app.models.enums import OfferStatus, OrderStatus


def _register_and_setup_master(
    client,
    admin_headers,
    phone: str,
    full_name: str,
    city: str,
    district: str,
    services: list[dict],
    approve: bool = True,
) -> tuple[dict, int, int]:
    """HTTP orqali usta ro'yxatdan o'tkazish, profil va xizmat qo'shish hamda tasdiqlash."""
    r_reg = client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "password": "password123",
            "full_name": full_name,
            "role": "master",
        },
    )
    assert r_reg.status_code == 201, r_reg.text
    reg_data = r_reg.json()
    headers = {"Authorization": f"Bearer {reg_data['access_token']}"}
    user_id = reg_data["user"]["id"]

    r_prof = client.post(
        "/api/v1/masters/profile",
        json={"bio": f"{full_name} tajribali usta", "city": city, "district": district},
        headers=headers,
    )
    assert r_prof.status_code == 201, r_prof.text
    profile_id = r_prof.json()["id"]

    if services:
        r_svc = client.put(
            "/api/v1/masters/me/services",
            json=services,
            headers=headers,
        )
        assert r_svc.status_code == 200, r_svc.text

    if approve:
        r_app = client.patch(
            f"/api/v1/admin/masters/{profile_id}/approval",
            json={"is_approved": True},
            headers=admin_headers,
        )
        assert r_app.status_code == 200, r_app.text

    return headers, profile_id, user_id


def _register_customer(client, phone: str, full_name: str = "Mijoz Alisher") -> tuple[dict, int]:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "phone": phone,
            "password": "password123",
            "full_name": full_name,
            "role": "customer",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


def _create_category_http(client, admin_headers, name="Santexnik", slug="santexnik") -> int:
    r = client.post(
        "/api/v1/admin/categories",
        json={"name": name, "slug": slug},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ==================== 3a. THE 9-STEP DEMO ====================


def test_e2e_nine_step_demo_and_automatic_followup(client, admin_headers):
    """3a: THE 9-STEP DEMO + automatic second order."""
    cat_id = _create_category_http(client, admin_headers, "Santexnik", "santexnik")

    # Ikkita mos usta (Chilonzor va Yunusobod)
    m1_headers, m1_pid, _ = _register_and_setup_master(
        client,
        admin_headers,
        phone="+998901001101",
        full_name="Aziz Santexnik",
        city="Toshkent",
        district="Chilonzor",
        services=[{"category_id": cat_id, "pricing_type": "quote"}],
        approve=True,
    )
    m2_headers, m2_pid, _ = _register_and_setup_master(
        client,
        admin_headers,
        phone="+998901001102",
        full_name="Jasur Santexnik",
        city="Toshkent",
        district="Yunusobod",
        services=[{"category_id": cat_id, "pricing_type": "quote"}],
        approve=True,
    )

    # 1. Customer registers and creates a manual santexnik order (Toshkent/Chilonzor)
    c_headers, _ = _register_customer(client, "+998902001101", "Mijoz Sardor")
    r_ord = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Oshxonada quvurdan suv oqmoqda",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Chilonzor 7-kvartal, 14-uy",
            "selection_mode": "manual",
        },
        headers=c_headers,
    )
    assert r_ord.status_code == 201
    order_id = r_ord.json()["id"]
    assert r_ord.json()["status"] == "searching"

    # 2. Customer picks a master
    r_sel = client.post(
        f"/api/v1/orders/{order_id}/select-master",
        json={"master_id": m1_pid},
        headers=c_headers,
    )
    assert r_sel.status_code == 200

    # 3. Master accepts
    r_acc = client.post(f"/api/v1/orders/{order_id}/accept", headers=m1_headers)
    assert r_acc.status_code == 200

    # 4. Master proposes a quote of 200000
    r_quote = client.post(
        f"/api/v1/orders/{order_id}/quotes",
        json={"price": 200_000, "note": "Quvur va kran almashtirish"},
        headers=m1_headers,
    )
    assert r_quote.status_code == 201
    quote_id = r_quote.json()["id"]
    assert r_quote.json()["price"] == 200_000

    # 5. Customer accepts quote
    r_qacc = client.post(
        f"/api/v1/orders/{order_id}/quotes/{quote_id}/accept",
        headers=c_headers,
    )
    assert r_qacc.status_code == 200
    assert r_qacc.json()["agreed_price"] == 200_000

    # 6. Master starts
    r_start = client.post(f"/api/v1/orders/{order_id}/start", headers=m1_headers)
    assert r_start.status_code == 200
    assert r_start.json()["status"] == "in_progress"

    # 7. Master completes
    r_comp = client.post(f"/api/v1/orders/{order_id}/complete", headers=m1_headers)
    assert r_comp.status_code == 200
    comp_body = r_comp.json()
    assert comp_body["status"] == "completed"
    assert comp_body["price"] == 200_000
    assert comp_body["commission_amount"] == 20_000
    assert comp_body["net"] == 180_000
    assert comp_body["net_amount"] == 180_000

    # Master earnings endpoint verifies numbers too
    r_earn = client.get("/api/v1/masters/me/earnings", headers=m1_headers)
    assert r_earn.status_code == 200
    earn = r_earn.json()
    assert earn["completed_count"] == 1
    assert earn["gross_total"] == 200_000
    assert earn["commission_total"] == 20_000
    assert earn["net_total"] == 180_000

    # Customer order detail: history order & customer NEVER sees commission_amount or master net
    r_cust_detail = client.get(f"/api/v1/orders/{order_id}", headers=c_headers)
    assert r_cust_detail.status_code == 200
    cust_detail = r_cust_detail.json()
    assert cust_detail["agreed_price"] == 200_000
    assert "commission_amount" not in cust_detail
    assert "net" not in cust_detail
    assert "net_amount" not in cust_detail
    assert "master_net" not in cust_detail

    r_cust_list = client.get("/api/v1/orders", headers=c_headers)
    assert r_cust_list.status_code == 200
    for item in r_cust_list.json():
        assert "commission_amount" not in item
        assert "net" not in item
        assert "master_net" not in item

    history_pairs = [(h["from_status"], h["to_status"]) for h in cust_detail["history"]]
    assert history_pairs == [
        (None, "searching"),
        ("searching", "assigned"),
        ("assigned", "in_progress"),
        ("in_progress", "completed"),
    ]

    # 8. Customer leaves a review -> master rating updated
    r_rev = client.post(
        f"/api/v1/orders/{order_id}/review",
        json={"rating": 5, "comment": "Ish juda toza bajarildi!"},
        headers=c_headers,
    )
    assert r_rev.status_code == 201

    r_master_pub = client.get(f"/api/v1/masters/{m1_pid}")
    assert r_master_pub.status_code == 200
    assert r_master_pub.json()["rating_avg"] == 5.0
    assert r_master_pub.json()["rating_count"] == 1

    # 9. Admin sees order, one cash payment and commission in /admin/orders and /admin/commissions
    r_adm_orders = client.get("/api/v1/admin/orders", headers=admin_headers)
    assert r_adm_orders.status_code == 200
    adm_list = [o for o in r_adm_orders.json() if o["id"] == order_id]
    assert len(adm_list) == 1
    assert adm_list[0]["agreed_price"] == 200_000
    assert adm_list[0]["commission_amount"] == 20_000

    r_adm_detail = client.get(f"/api/v1/admin/orders/{order_id}", headers=admin_headers)
    assert r_adm_detail.status_code == 200
    adm_det = r_adm_detail.json()
    assert adm_det["payment"] is not None
    assert adm_det["payment"]["method"] == "cash"
    assert adm_det["payment"]["amount"] == 200_000
    assert adm_det["payment"]["status"] == "paid"
    assert adm_det["commission_amount"] == 20_000

    r_adm_comm = client.get("/api/v1/admin/commissions", headers=admin_headers)
    assert r_adm_comm.status_code == 200
    comm_data = r_adm_comm.json()
    assert comm_data["total_completed_orders"] == 1
    assert comm_data["gross_total"] == 200_000
    assert comm_data["commission_total"] == 20_000
    assert len(comm_data["orders"]) == 1
    assert comm_data["orders"][0]["id"] == order_id
    assert comm_data["orders"][0]["master_net"] == 180_000
    assert comm_data["orders"][0]["payment_amount"] == 200_000
    assert comm_data["orders"][0]["payment_status"] == "paid"

    # Second order in AUTOMATIC mode: system offers it to the best eligible master (m1_pid)
    r_auto = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Ikkinchi buyurtma: vannada kran oqyapti",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Chilonzor 8-kvartal, 3-uy",
            "selection_mode": "automatic",
        },
        headers=c_headers,
    )
    assert r_auto.status_code == 201
    auto_body = r_auto.json()
    assert len(auto_body["offers"]) == 1
    assert auto_body["offers"][0]["master_id"] == m1_pid
    assert auto_body["offers"][0]["status"] == "pending"


# ==================== 3b. Fixed-price flow ====================


def test_e2e_fixed_price_flow(client, admin_headers):
    """3b: Fixed-price flow: price is set automatically on accept and cannot be changed afterwards;
    start works without a quote."""
    cat_id = _create_category_http(client, admin_headers, "Elektrik", "elektrik")
    m_headers, m_pid, _ = _register_and_setup_master(
        client,
        admin_headers,
        phone="+998901002201",
        full_name="Fixed Usta",
        city="Toshkent",
        district="Chilonzor",
        services=[{"category_id": cat_id, "pricing_type": "fixed", "base_price": 120_000}],
        approve=True,
    )
    c_headers, _ = _register_customer(client, "+998902002201")

    r_ord = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Rozetka o'rnatish kerak",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Chilonzor 1-kv, 2-uy",
            "selection_mode": "manual",
        },
        headers=c_headers,
    )
    assert r_ord.status_code == 201
    order_id = r_ord.json()["id"]

    assert (
        client.post(
            f"/api/v1/orders/{order_id}/select-master",
            json={"master_id": m_pid},
            headers=c_headers,
        ).status_code
        == 200
    )

    # Accept sets agreed_price automatically
    r_acc = client.post(f"/api/v1/orders/{order_id}/accept", headers=m_headers)
    assert r_acc.status_code == 200

    r_det = client.get(f"/api/v1/orders/{order_id}", headers=c_headers)
    assert r_det.status_code == 200
    assert r_det.json()["agreed_price"] == 120_000

    # Price cannot be changed afterwards via quote -> 409
    r_quote = client.post(
        f"/api/v1/orders/{order_id}/quotes",
        json={"price": 180_000, "note": "Qimmatroq"},
        headers=m_headers,
    )
    assert r_quote.status_code == 409

    # Start works without a quote
    r_start = client.post(f"/api/v1/orders/{order_id}/start", headers=m_headers)
    assert r_start.status_code == 200
    assert r_start.json()["status"] == "in_progress"


# ==================== 3c. Automatic rotation ====================


def test_e2e_automatic_rotation_and_all_reject_cancel(client, admin_headers):
    """3c: Automatic rotation: master A rejects -> master B gets the offer -> B accepts;
    A is never offered again; when everyone rejects the order stays searching and customer can cancel."""
    cat_id = _create_category_http(client, admin_headers)

    # Master A in Chilonzor (higher district bonus), Master B in Yunusobod
    mA_headers, mA_pid, _ = _register_and_setup_master(
        client,
        admin_headers,
        phone="+998901003301",
        full_name="Usta A",
        city="Toshkent",
        district="Chilonzor",
        services=[{"category_id": cat_id, "pricing_type": "fixed", "base_price": 100_000}],
        approve=True,
    )
    mB_headers, mB_pid, _ = _register_and_setup_master(
        client,
        admin_headers,
        phone="+998901003302",
        full_name="Usta B",
        city="Toshkent",
        district="Yunusobod",
        services=[{"category_id": cat_id, "pricing_type": "fixed", "base_price": 100_000}],
        approve=True,
    )
    c_headers, _ = _register_customer(client, "+998902003301")

    # Scenario 1: A rejects -> B gets offer -> B accepts
    r_ord1 = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Avtomatik buyurtma 1",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "1-uy",
            "selection_mode": "automatic",
        },
        headers=c_headers,
    )
    assert r_ord1.status_code == 201
    oid1 = r_ord1.json()["id"]
    assert r_ord1.json()["offers"][0]["master_id"] == mA_pid

    r_rejA = client.post(f"/api/v1/orders/{oid1}/reject", headers=mA_headers)
    assert r_rejA.status_code == 200
    assert r_rejA.json()["next_master_offered"] is True

    # Master B now has the pending offer; Master A has none
    mA_orders = client.get("/api/v1/masters/me/orders", headers=mA_headers).json()
    assert mA_orders["pending_offers"] == []
    mB_orders = client.get("/api/v1/masters/me/orders", headers=mB_headers).json()
    assert [o["order_id"] for o in mB_orders["pending_offers"]] == [oid1]

    # Master B accepts
    r_accB = client.post(f"/api/v1/orders/{oid1}/accept", headers=mB_headers)
    assert r_accB.status_code == 200

    det1 = client.get(f"/api/v1/orders/{oid1}", headers=c_headers).json()
    assert det1["status"] == "assigned"
    assert det1["master_id"] == mB_pid

    # Scenario 2: Everyone rejects -> order stays searching -> customer cancels
    r_ord2 = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Avtomatik buyurtma 2",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "2-uy",
            "selection_mode": "automatic",
        },
        headers=c_headers,
    )
    assert r_ord2.status_code == 201
    oid2 = r_ord2.json()["id"]

    # Master A rejects -> Master B offered
    assert client.post(f"/api/v1/orders/{oid2}/reject", headers=mA_headers).json()["next_master_offered"] is True
    # Master B rejects -> no one left (Master A is never offered again)
    r_rejB2 = client.post(f"/api/v1/orders/{oid2}/reject", headers=mB_headers)
    assert r_rejB2.status_code == 200
    assert r_rejB2.json()["next_master_offered"] is False

    det2 = client.get(f"/api/v1/orders/{oid2}", headers=c_headers).json()
    assert det2["status"] == "searching"
    assert len(det2["offers"]) == 2
    assert all(o["status"] == "rejected" for o in det2["offers"])

    # Customer can cancel
    r_cancel = client.post(f"/api/v1/orders/{oid2}/cancel", headers=c_headers)
    assert r_cancel.status_code == 200
    assert r_cancel.json()["status"] == "cancelled"


# ==================== 3d. Cancel paths ====================


def test_e2e_customer_cancel_paths_and_no_payment(client, admin_headers):
    """3d (customer part): customer cancels in searching and assigned; cannot cancel
    in_progress or completed; no Payment exists for a cancelled order."""
    cat_id = _create_category_http(client, admin_headers)
    m_headers, m_pid, _ = _register_and_setup_master(
        client,
        admin_headers,
        phone="+998901004401",
        full_name="Usta Cancel",
        city="Toshkent",
        district="Chilonzor",
        services=[{"category_id": cat_id, "pricing_type": "fixed", "base_price": 100_000}],
        approve=True,
    )
    c_headers, _ = _register_customer(client, "+998902004401")

    def _make_order(desc: str) -> int:
        r = client.post(
            "/api/v1/orders",
            json={
                "category_id": cat_id,
                "description": desc,
                "city": "Toshkent",
                "district": "Chilonzor",
                "address": "Manzil",
                "selection_mode": "manual",
            },
            headers=c_headers,
        )
        assert r.status_code == 201
        return r.json()["id"]

    # 1. Cancel in searching
    oid_search = _make_order("Searching cancel")
    r_c1 = client.post(f"/api/v1/orders/{oid_search}/cancel", headers=c_headers)
    assert r_c1.status_code == 200
    assert r_c1.json()["status"] == "cancelled"
    assert client.get(f"/api/v1/admin/orders/{oid_search}", headers=admin_headers).json()["payment"] is None

    # 2. Cancel in assigned
    oid_assign = _make_order("Assigned cancel")
    client.post(f"/api/v1/orders/{oid_assign}/select-master", json={"master_id": m_pid}, headers=c_headers)
    client.post(f"/api/v1/orders/{oid_assign}/accept", headers=m_headers)
    r_c2 = client.post(f"/api/v1/orders/{oid_assign}/cancel", headers=c_headers)
    assert r_c2.status_code == 200
    assert r_c2.json()["status"] == "cancelled"
    assert client.get(f"/api/v1/admin/orders/{oid_assign}", headers=admin_headers).json()["payment"] is None

    # 3. Customer cannot cancel in_progress or completed
    oid_prog = _make_order("In progress order")
    client.post(f"/api/v1/orders/{oid_prog}/select-master", json={"master_id": m_pid}, headers=c_headers)
    client.post(f"/api/v1/orders/{oid_prog}/accept", headers=m_headers)
    client.post(f"/api/v1/orders/{oid_prog}/start", headers=m_headers)

    r_c_prog = client.post(f"/api/v1/orders/{oid_prog}/cancel", headers=c_headers)
    assert r_c_prog.status_code in (403, 409)

    client.post(f"/api/v1/orders/{oid_prog}/complete", headers=m_headers)
    r_c_comp = client.post(f"/api/v1/orders/{oid_prog}/cancel", headers=c_headers)
    assert r_c_comp.status_code in (403, 409)


def test_e2e_admin_can_cancel_in_progress_order(client, admin_headers):
    """3d (admin part): admin can cancel in_progress; no Payment exists for a cancelled order."""
    cat_id = _create_category_http(client, admin_headers)
    m_headers, m_pid, _ = _register_and_setup_master(
        client,
        admin_headers,
        phone="+998901004402",
        full_name="Usta AdminCancel",
        city="Toshkent",
        district="Chilonzor",
        services=[{"category_id": cat_id, "pricing_type": "fixed", "base_price": 100_000}],
        approve=True,
    )
    c_headers, _ = _register_customer(client, "+998902004402")

    r_ord = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Admin bekor qiladigan buyurtma",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "Manzil",
            "selection_mode": "manual",
        },
        headers=c_headers,
    )
    oid = r_ord.json()["id"]
    client.post(f"/api/v1/orders/{oid}/select-master", json={"master_id": m_pid}, headers=c_headers)
    client.post(f"/api/v1/orders/{oid}/accept", headers=m_headers)
    client.post(f"/api/v1/orders/{oid}/start", headers=m_headers)

    # Admin attempts to cancel via HTTP
    admin_me = client.get("/api/v1/auth/me", headers=admin_headers).json()
    r_cancel = client.post(f"/api/v1/admin/orders/{oid}/cancel", headers=admin_headers)
    assert r_cancel.status_code == 200

    adm_det = client.get(f"/api/v1/admin/orders/{oid}", headers=admin_headers).json()
    assert adm_det["status"] == "cancelled"
    assert adm_det["payment"] is None
    assert adm_det["history"][-1]["from_status"] == "in_progress"
    assert adm_det["history"][-1]["to_status"] == "cancelled"
    assert adm_det["history"][-1]["changed_by"] == admin_me["id"]


# ==================== 3e. Visibility ====================


def test_e2e_master_visibility_approval_blocking_and_availability(client, admin_headers):
    """3e: An unapproved master and a blocked master are absent from GET /masters and
    from automatic matching; after admin approval they appear; an unavailable (busy)
    master does not receive new offers."""
    cat_id = _create_category_http(client, admin_headers)

    # Unapproved master
    m_headers, m_pid, m_uid = _register_and_setup_master(
        client,
        admin_headers,
        phone="+998901005501",
        full_name="Ko'rinmas Usta",
        city="Toshkent",
        district="Chilonzor",
        services=[{"category_id": cat_id, "pricing_type": "fixed", "base_price": 100_000}],
        approve=False,
    )
    c_headers, _ = _register_customer(client, "+998902005501")

    # 1. Unapproved master is absent from GET /masters and automatic matching
    assert client.get("/api/v1/masters").json() == []
    r_ord1 = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Avto buyurtma 1",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "1-uy",
            "selection_mode": "automatic",
        },
        headers=c_headers,
    )
    assert r_ord1.status_code == 201
    assert r_ord1.json()["offers"] == []
    assert r_ord1.json()["note"] == "Mos usta topilmadi"

    # 2. Admin approves master -> appears in GET /masters
    client.patch(
        f"/api/v1/admin/masters/{m_pid}/approval",
        json={"is_approved": True},
        headers=admin_headers,
    )
    assert [m["id"] for m in client.get("/api/v1/masters").json()] == [m_pid]

    # 3. Admin blocks master -> absent from GET /masters and automatic matching
    client.patch(
        f"/api/v1/admin/users/{m_uid}/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert client.get("/api/v1/masters").json() == []
    r_ord2 = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Avto buyurtma 2",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "2-uy",
            "selection_mode": "automatic",
        },
        headers=c_headers,
    )
    assert r_ord2.json()["offers"] == []

    # 4. Admin unblocks master -> appears again and receives automatic offers
    client.patch(
        f"/api/v1/admin/users/{m_uid}/status",
        json={"is_active": True},
        headers=admin_headers,
    )
    assert [m["id"] for m in client.get("/api/v1/masters").json()] == [m_pid]
    r_ord3 = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Avto buyurtma 3",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "3-uy",
            "selection_mode": "automatic",
        },
        headers=c_headers,
    )
    assert len(r_ord3.json()["offers"]) == 1
    assert r_ord3.json()["offers"][0]["master_id"] == m_pid

    # 5. Master marks self unavailable (busy) -> does not receive new offers
    client.patch(
        "/api/v1/masters/me/availability",
        json={"is_available": False},
        headers=m_headers,
    )
    assert client.get("/api/v1/masters").json() == []
    r_ord4 = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Avto buyurtma 4",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "4-uy",
            "selection_mode": "automatic",
        },
        headers=c_headers,
    )
    assert r_ord4.json()["offers"] == []
    assert r_ord4.json()["note"] == "Mos usta topilmadi"


# ==================== 3f. Admin manual assignment ====================


def test_e2e_admin_manual_assignment_and_409_when_already_assigned(client, admin_headers):
    """3f: Admin manual assignment of a searching order and the 409 when it is already assigned."""
    cat_id = _create_category_http(client, admin_headers)
    _, m1_pid, _ = _register_and_setup_master(
        client,
        admin_headers,
        phone="+998901006601",
        full_name="Usta 1",
        city="Toshkent",
        district="Chilonzor",
        services=[{"category_id": cat_id, "pricing_type": "fixed", "base_price": 100_000}],
        approve=True,
    )
    _, m2_pid, _ = _register_and_setup_master(
        client,
        admin_headers,
        phone="+998901006602",
        full_name="Usta 2",
        city="Toshkent",
        district="Chilonzor",
        services=[{"category_id": cat_id, "pricing_type": "fixed", "base_price": 100_000}],
        approve=True,
    )
    c_headers, _ = _register_customer(client, "+998902006601")

    r_ord = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Admin biriktiradigan buyurtma",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "1-uy",
            "selection_mode": "manual",
        },
        headers=c_headers,
    )
    order_id = r_ord.json()["id"]

    # First admin assignment -> 200
    r_assign1 = client.patch(
        f"/api/v1/admin/orders/{order_id}/assign",
        json={"master_id": m1_pid},
        headers=admin_headers,
    )
    assert r_assign1.status_code == 200
    assert r_assign1.json()["status"] == "assigned"
    assert r_assign1.json()["master_id"] == m1_pid
    assert r_assign1.json()["agreed_price"] == 100_000

    # Second admin assignment when already assigned -> 409
    r_assign2 = client.patch(
        f"/api/v1/admin/orders/{order_id}/assign",
        json={"master_id": m2_pid},
        headers=admin_headers,
    )
    assert r_assign2.status_code == 409


# ==================== 3g. Price protection ====================


def test_e2e_price_protection(client, admin_headers):
    """3g: start without a confirmed price -> 409; a quote cannot be accepted twice;
    a rejected old quote cannot be accepted."""
    cat_id = _create_category_http(client, admin_headers)
    m_headers, m_pid, _ = _register_and_setup_master(
        client,
        admin_headers,
        phone="+998901007701",
        full_name="Quote Usta",
        city="Toshkent",
        district="Chilonzor",
        services=[{"category_id": cat_id, "pricing_type": "quote"}],
        approve=True,
    )
    c_headers, _ = _register_customer(client, "+998902007701")

    r_ord = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Narx himoyasi testi",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "1-uy",
            "selection_mode": "manual",
        },
        headers=c_headers,
    )
    oid = r_ord.json()["id"]
    client.post(f"/api/v1/orders/{oid}/select-master", json={"master_id": m_pid}, headers=c_headers)
    client.post(f"/api/v1/orders/{oid}/accept", headers=m_headers)

    # 1. Start without confirmed price -> 409
    assert client.post(f"/api/v1/orders/{oid}/start", headers=m_headers).status_code == 409

    # 2. First quote proposed, then rejected by customer -> cannot be accepted
    q1 = client.post(
        f"/api/v1/orders/{oid}/quotes",
        json={"price": 250_000, "note": "Birinchi narx"},
        headers=m_headers,
    ).json()
    assert client.post(f"/api/v1/orders/{oid}/quotes/{q1['id']}/reject", headers=c_headers).status_code == 200
    assert client.post(f"/api/v1/orders/{oid}/quotes/{q1['id']}/accept", headers=c_headers).status_code == 409

    # 3. Second quote proposed, then replaced by third quote -> second quote cannot be accepted
    q2 = client.post(
        f"/api/v1/orders/{oid}/quotes",
        json={"price": 220_000, "note": "Ikkinchi narx"},
        headers=m_headers,
    ).json()
    q3 = client.post(
        f"/api/v1/orders/{oid}/quotes",
        json={"price": 190_000, "note": "Uchinchi narx"},
        headers=m_headers,
    ).json()
    assert client.post(f"/api/v1/orders/{oid}/quotes/{q2['id']}/accept", headers=c_headers).status_code == 409

    # 4. Accept active quote (q3) -> 200; accepting q3 a second time -> 409
    assert client.post(f"/api/v1/orders/{oid}/quotes/{q3['id']}/accept", headers=c_headers).status_code == 200
    assert client.post(f"/api/v1/orders/{oid}/quotes/{q3['id']}/accept", headers=c_headers).status_code == 409


# ==================== 3h. Concurrency (two sessions) ====================


def test_e2e_concurrency_two_masters_accept_same_order(client, db, admin_headers):
    """3h: Concurrency (use two sessions): two masters accept the same order at the same time ->
    exactly one wins, the other gets 409."""
    cat_id = _create_category_http(client, admin_headers)
    m1_headers, m1_pid, _ = _register_and_setup_master(
        client,
        admin_headers,
        phone="+998901008801",
        full_name="Race Usta 1",
        city="Toshkent",
        district="Chilonzor",
        services=[{"category_id": cat_id, "pricing_type": "fixed", "base_price": 100_000}],
        approve=True,
    )
    m2_headers, m2_pid, _ = _register_and_setup_master(
        client,
        admin_headers,
        phone="+998901008802",
        full_name="Race Usta 2",
        city="Toshkent",
        district="Chilonzor",
        services=[{"category_id": cat_id, "pricing_type": "fixed", "base_price": 100_000}],
        approve=True,
    )
    c_headers, _ = _register_customer(client, "+998902008801")

    r_ord = client.post(
        "/api/v1/orders",
        json={
            "category_id": cat_id,
            "description": "Concurrency poyga buyurtmasi",
            "city": "Toshkent",
            "district": "Chilonzor",
            "address": "1-uy",
            "selection_mode": "manual",
        },
        headers=c_headers,
    )
    oid = r_ord.json()["id"]

    # Seed two pending offers for the two masters on the same order
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    with SessionLocal() as seed_session:
        seed_session.add_all(
            [
                models.OrderOffer(
                    order_id=oid,
                    master_id=m1_pid,
                    status=OfferStatus.PENDING,
                    expires_at=expires,
                ),
                models.OrderOffer(
                    order_id=oid,
                    master_id=m2_pid,
                    status=OfferStatus.PENDING,
                    expires_at=expires,
                ),
            ]
        )
        seed_session.commit()

    # Two independent HTTP client sessions attempt to accept the same order
    with TestClient(app) as client_a, TestClient(app) as client_b:
        res_a = client_a.post(f"/api/v1/orders/{oid}/accept", headers=m1_headers)
        res_b = client_b.post(f"/api/v1/orders/{oid}/accept", headers=m2_headers)

    statuses = sorted([res_a.status_code, res_b.status_code])
    assert statuses == [200, 409], f"Expected one 200 and one 409, got {statuses}"

    det = client.get(f"/api/v1/orders/{oid}", headers=c_headers).json()
    assert det["status"] == "assigned"
    assert det["master_id"] in (m1_pid, m2_pid)
