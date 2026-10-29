from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.core.config import settings
from app.models import User
from app.schemas.geo import GeoCandidate, GeoConfigOut
from app.services import geo as geo_service

router = APIRouter(prefix="/geo", tags=["geo"])


@router.get("/config", response_model=GeoConfigOut)
def get_geo_config():
    """Frontend xarita vidjeti uchun ommaviy sozlama (kalit bo'sh bo'lishi mumkin)."""
    return GeoConfigOut(yandex_maps_key=settings.YANDEX_API_KEY)


@router.get("/search", response_model=list[GeoCandidate])
def search_address(
    q: str = Query(..., min_length=3, max_length=255),
    user: User = Depends(get_current_user),
):
    """Manzil matnidan koordinata nomzodlarini qidiradi (Yandex Geocoder proxy)."""
    return geo_service.geocode(q)
