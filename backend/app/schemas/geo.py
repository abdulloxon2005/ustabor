from pydantic import BaseModel


class GeoCandidate(BaseModel):
    address: str
    latitude: float
    longitude: float


class GeoConfigOut(BaseModel):
    yandex_maps_key: str
