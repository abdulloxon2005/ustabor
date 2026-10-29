"""Masofa hisoblash va Yandex Geocoder proxy.

Yandex API kaliti faqat shu yerda, backendda ishlatiladi — frontendga chiqarilmaydi.
"""

import math

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

GEOCODE_URL = "https://geocode-maps.yandex.ru/1.x/"
EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Ikki koordinata orasidagi masofa (katta doira, km)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def geocode(query: str, results: int = 5) -> list[dict]:
    """Manzil matnidan nomzodlar ro'yxati: [{"address", "latitude", "longitude"}, ...].

    Yandex API kaliti sozlanmagan bo'lsa 503 qaytaradi.
    Tarmoq/Yandex xatoligida 502 qaytaradi (so'rovchiga tushunarli xabar bilan).
    """
    if not settings.YANDEX_API_KEY:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Xarita xizmati sozlanmagan (YANDEX_API_KEY yo'q)",
        )

    try:
        resp = httpx.get(
            GEOCODE_URL,
            params={
                "apikey": settings.YANDEX_API_KEY,
                "geocode": query,
                "format": "json",
                "results": results,
            },
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Xarita xizmatiga ulanib bo'lmadi"
        )

    members = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
    candidates: list[dict] = []
    for member in members:
        geo_obj = member.get("GeoObject", {})
        pos = geo_obj.get("Point", {}).get("pos")
        if not pos:
            continue
        lon_str, lat_str = pos.split()
        address = (
            geo_obj.get("metaDataProperty", {})
            .get("GeocoderMetaData", {})
            .get("text", query)
        )
        candidates.append(
            {
                "address": address,
                "latitude": float(lat_str),
                "longitude": float(lon_str),
            }
        )
    return candidates
