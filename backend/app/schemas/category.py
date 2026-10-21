import re

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def slugify(name: str) -> str:
    """'Ta'mirlash va qurilish' -> 'tamirlash-va-qurilish'."""
    s = name.lower()
    for ch in ("'", "ʻ", "ʼ", "’", "`"):
        s = s.replace(ch, "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    is_active: bool


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    slug: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Nom kamida 2 ta belgidan iborat bo'lishi kerak")
        return v

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        v = v.strip()
        if not SLUG_RE.fullmatch(v):
            raise ValueError(
                "Slug faqat kichik lotin harflari, raqamlar va tire (-) dan iborat bo'lishi kerak"
            )
        return v


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    is_active: StrictBool | None = None

    @model_validator(mode="before")
    @classmethod
    def _non_empty_payload(cls, data):
        if isinstance(data, dict) and not data:
            raise ValueError("Kamida bitta maydon yuborilishi kerak")
        return data

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Nom kamida 2 ta belgidan iborat bo'lishi kerak")
        return v
