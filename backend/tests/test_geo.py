"""Yandex geokodlash proxy, Haversine masofa va matching'dagi masofa bonusi.

Haqiqiy tarmoq so'rovi yuborilmaydi: httpx.get har doim monkeypatch qilinadi.
"""

import httpx
import pytest

from app import models
from app.core.config import settings
from app.core.security import hash_password
from app.models.enums import OrderStatus, Role, SelectionMode
from app.services import geo, matching

GEO_SEARCH = "/api/v1/geo/search"


# ====== Haversine ======


def test_haversine_same_point_is_zero():
    assert geo.haversine_km(41.3111, 69.2406, 41.3111, 69.2406) == pytest.approx(0.0, abs=1e-6)


def test_haversine_one_degree_latitude_is_about_111_km():
    # Ekvatorga yaqin, bir xil uzunlik: 1 gradus kenglik ~ 111.2 km
    d = geo.haversine_km(0.0, 0.0, 1.0, 0.0)
    assert d == pytest.approx(111.2, abs=1.0)


def test_haversine_symmetric():
    d1 = geo.haversine_km(41.3, 69.2, 39.65, 66.97)
    d2 = geo.haversine_km(39.65, 66.97, 41.3, 69.2)
    assert d1 == pytest.approx(d2, abs=1e-9)


# ====== Geocode service (tarmoqsiz) ======


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("xato", request=None, response=self)

    def json(self):
        return self._json


_YANDEX_OK_RESPONSE = {
    "response": {
        "GeoObjectCollection": {
            "featureMember": [
                {
                    "GeoObject": {
                        "Point": {"pos": "69.240562 41.311151"},
                        "metaDataProperty": {
                            "GeocoderMetaData": {"text": "Toshkent, Chilonzor tumani"}
                        },
                    }
                },
                {
                    "GeoObject": {
                        "Point": {"pos": "69.250000 41.300000"},
                        "metaDataProperty": {
                            "GeocoderMetaData": {"text": "Toshkent, Yunusobod tumani"}
                        },
                    }
                },
            ]
        }
    }
}


def test_geocode_without_api_key_raises_503():
    assert settings.YANDEX_GEOCODER_API_KEY == ""
    with pytest.raises(Exception) as exc_info:
        geo.geocode("Toshkent")
    assert getattr(exc_info.value, "status_code", None) == 503


def test_geocode_parses_yandex_response(monkeypatch):
    monkeypatch.setattr(geo.settings, "YANDEX_GEOCODER_API_KEY", "test-key")
    monkeypatch.setattr(geo.httpx, "get", lambda *a, **k: _FakeResponse(_YANDEX_OK_RESPONSE))

    results = geo.geocode("Toshkent, Chilonzor")
    assert len(results) == 2
    assert results[0]["address"] == "Toshkent, Chilonzor tumani"
    assert results[0]["latitude"] == pytest.approx(41.311151)
    assert results[0]["longitude"] == pytest.approx(69.240562)


def test_geocode_empty_results():
    empty = {"response": {"GeoObjectCollection": {"featureMember": []}}}

    def _fake_get(*a, **k):
        return _FakeResponse(empty)

    import app.services.geo as geo_module

    geo_module.settings.YANDEX_GEOCODER_API_KEY = "test-key"
    geo_module.httpx.get = _fake_get
    try:
        results = geo.geocode("Nomavjud manzil")
        assert results == []
    finally:
        geo_module.settings.YANDEX_GEOCODER_API_KEY = ""


def test_geocode_http_error_raises_502(monkeypatch):
    monkeypatch.setattr(geo.settings, "YANDEX_GEOCODER_API_KEY", "test-key")

    def _raise(*a, **k):
        raise httpx.ConnectError("ulanib bo'lmadi")

    monkeypatch.setattr(geo.httpx, "get", _raise)

    with pytest.raises(Exception) as exc_info:
        geo.geocode("Toshkent")
    assert getattr(exc_info.value, "status_code", None) == 502


# ====== GET /api/v1/geo/config endpoint ======


def test_geo_config_is_public_and_reflects_settings(client, monkeypatch):
    r_empty = client.get("/api/v1/geo/config")
    assert r_empty.status_code == 200
    assert r_empty.json() == {"yandex_maps_key": ""}

    monkeypatch.setattr(geo.settings, "YANDEX_MAPS_JS_API_KEY", "test-key")
    r_set = client.get("/api/v1/geo/config")
    assert r_set.json() == {"yandex_maps_key": "test-key"}


# ====== GET /api/v1/geo/search endpoint ======


def test_geo_search_requires_auth(client):
    r = client.get(GEO_SEARCH + "?q=Toshkent")
    assert r.status_code == 401


def test_geo_search_rejects_short_query(client, signup):
    h, _ = signup("customer", "+998901240001", "Mijoz Geo")
    r = client.get(GEO_SEARCH + "?q=ab", headers=h)
    assert r.status_code == 422


def test_geo_search_returns_candidates(client, signup, monkeypatch):
    monkeypatch.setattr(geo.settings, "YANDEX_GEOCODER_API_KEY", "test-key")
    monkeypatch.setattr(geo.httpx, "get", lambda *a, **k: _FakeResponse(_YANDEX_OK_RESPONSE))

    h, _ = signup("customer", "+998901240002", "Mijoz Geo 2")
    r = client.get(GEO_SEARCH + "?q=Toshkent, Chilonzor", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 2
    assert body[0]["address"] == "Toshkent, Chilonzor tumani"


def test_geo_search_without_key_returns_503(client, signup):
    h, _ = signup("customer", "+998901240003", "Mijoz Geo 3")
    r = client.get(GEO_SEARCH + "?q=Toshkent shahri", headers=h)
    assert r.status_code == 503


# ====== score_master masofa bonusi (backward-compatible) ======


def _user(db, phone, role=Role.MASTER, full_name="Test Usta"):
    u = models.User(
        phone=phone, password_hash=hash_password("secret123"), full_name=full_name, role=role
    )
    db.add(u)
    db.flush()
    return u


def _master(db, user, latitude=None, longitude=None, city="Toshkent", district="Yunusobod"):
    mp = models.MasterProfile(
        user_id=user.id,
        city=city,
        district=district,
        is_approved=True,
        is_available=True,
        rating_avg=4.0,
        rating_count=10,
        latitude=latitude,
        longitude=longitude,
    )
    db.add(mp)
    db.flush()
    return mp


def _order(db, customer, category, latitude=None, longitude=None, city="Toshkent", district="Yunusobod"):
    o = models.Order(
        customer_id=customer.id,
        category_id=category.id,
        description="Test buyurtma",
        city=city,
        district=district,
        address="Test manzil",
        status=OrderStatus.SEARCHING,
        selection_mode=SelectionMode.AUTOMATIC,
        latitude=latitude,
        longitude=longitude,
    )
    db.add(o)
    db.flush()
    return o


def _category(db, name="Santexnik", slug="santexnik_geo"):
    c = models.Category(name=name, slug=slug, is_active=True)
    db.add(c)
    db.flush()
    return c


def test_score_master_without_coords_unaffected(db):
    """Koordinata yo'q bo'lsa distance_bonus=0, score eski formula bilan bir xil."""
    cat = _category(db)
    customer = _user(db, "+998901240010", role=Role.CUSTOMER, full_name="Mijoz")
    master_user = _user(db, "+998901240011")
    master = _master(db, master_user)
    order = _order(db, customer, cat)

    score = matching.score_master(master, order, global_avg=4.0)

    bayes = matching.bayes_rating(master.rating_avg, master.rating_count, 4.0)
    bayes_norm = bayes / 5.0
    district_bonus = 1.0  # bir xil shahar va tuman
    new_bonus = 0.0  # rating_count=10 >= threshold(3)
    expected = (
        settings.MATCH_W_RATING * bayes_norm
        + settings.MATCH_W_DISTRICT * district_bonus
        + settings.MATCH_W_NEW_BONUS * new_bonus
    )
    assert score == pytest.approx(expected)


def test_score_master_closer_master_scores_higher(db):
    cat = _category(db, name="Santexnik2", slug="santexnik_geo2")
    customer = _user(db, "+998901240012", role=Role.CUSTOMER, full_name="Mijoz 2")
    order = _order(db, customer, cat, latitude=41.3111, longitude=69.2406)

    near_user = _user(db, "+998901240013", full_name="Yaqin Usta")
    near_master = _master(db, near_user, latitude=41.3150, longitude=69.2450)  # ~0.6 km
    near_master.location_sharing_enabled = True

    far_user = _user(db, "+998901240014", full_name="Uzoq Usta")
    far_master = _master(db, far_user, latitude=41.5000, longitude=69.5000)  # ~25+ km
    far_master.location_sharing_enabled = True

    score_near = matching.score_master(near_master, order, global_avg=4.0)
    score_far = matching.score_master(far_master, order, global_avg=4.0)

    assert score_near > score_far


def test_score_master_one_sided_coords_gives_zero_distance_bonus(db):
    """Faqat bir tomonda koordinata bo'lsa, masofa bonusi 0 (xatoga olib kelmaydi)."""
    cat = _category(db, name="Santexnik3", slug="santexnik_geo3")
    customer = _user(db, "+998901240015", role=Role.CUSTOMER, full_name="Mijoz 3")
    order = _order(db, customer, cat, latitude=41.3111, longitude=69.2406)

    master_user = _user(db, "+998901240016", full_name="Usta Koordinatasiz")
    master = _master(db, master_user, latitude=None, longitude=None)

    score = matching.score_master(master, order, global_avg=4.0)

    bayes = matching.bayes_rating(master.rating_avg, master.rating_count, 4.0)
    bayes_norm = bayes / 5.0
    expected = settings.MATCH_W_RATING * bayes_norm + settings.MATCH_W_DISTRICT * 1.0
    assert score == pytest.approx(expected)
