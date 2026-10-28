"""Rasm yuklash — hozircha lokal disk (backend/uploads/), /media/ orqali ko'rsatiladi
(app/main.py da StaticFiles mount qilingan).

Validatsiya: ruxsat etilgan kengaytma/MIME turi + magic bytes, maksimal hajm,
tasodifiy fayl nomi (yuklangan nomga ishonmaslik — xavfsizlik).
"""

import secrets
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

_MAGIC_BYTES: tuple[bytes, ...] = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
)

UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"

INVALID_IMAGE = "Faqat JPG yoki PNG formatidagi rasm yuklash mumkin"
TOO_LARGE = "Rasm hajmi 5 MB dan oshmasligi kerak"


def _subdir(name: str) -> Path:
    d = UPLOADS_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    return d


async def save_image(file: UploadFile, subdir: str) -> str:
    """Yuklangan rasmni tekshiradi va saqlaydi.

    Qaytaradi: uploads/ ga nisbatan yo'l (masalan "order_photos/ab12cd34.jpg").
    Noto'g'ri fayl -> 422.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS or file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, INVALID_IMAGE)

    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, TOO_LARGE)
    if not content or not any(content.startswith(sig) for sig in _MAGIC_BYTES):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, INVALID_IMAGE)

    filename = f"{secrets.token_hex(16)}{ext}"
    dest = _subdir(subdir) / filename
    dest.write_bytes(content)

    return f"{subdir}/{filename}"


def delete_image(relative_path: str) -> None:
    path = (UPLOADS_DIR / relative_path).resolve()
    if UPLOADS_DIR.resolve() not in path.parents:
        return  # xavfsizlik: uploads/ tashqarisidagi hech narsa o'chirilmaydi
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def url_for(relative_path: str) -> str:
    return f"/media/{relative_path}"
