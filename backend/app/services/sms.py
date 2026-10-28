"""SMS yuborish xizmati — HOZIRCHA MOCK.

Haqiqiy SMS yuborilmaydi: xabar log'ga yoziladi va (faqat testlar/debug
uchun) xotiradagi _outbox ro'yxatiga qo'shiladi.

PRODUCTIONGA CHIQISHDAN OLDIN: send_sms() funksiyasini haqiqiy provayderga
(masalan Eskiz.uz, Play Mobile) ulash kerak — qolgan kod (otp.py, notify.py)
o'zgarishsiz ishlayveradi, chunki ular faqat shu funksiyani chaqiradi.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("sms")

# Faqat testlar/debug uchun: so'nggi yuborilgan xabarlar (eng yangisi oxirida).
_outbox: list[dict] = []
_OUTBOX_LIMIT = 200

# Qo'lda sinash uchun: uvicorn konsoli stdout buferlashi tufayli ishonchsiz
# bo'lgani sababli, xabar alohida faylga ham yoziladi (.gitignore'da).
_OUTBOX_FILE = Path(__file__).resolve().parent.parent.parent / "sms_outbox.log"


def send_sms(phone: str, text: str) -> None:
    logger.info("SMS -> %s: %s", phone, text)
    _outbox.append({"phone": phone, "text": text})
    if len(_outbox) > _OUTBOX_LIMIT:
        del _outbox[: len(_outbox) - _OUTBOX_LIMIT]
    try:
        with open(_OUTBOX_FILE, "a", encoding="utf-8") as f:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {phone}: {text}\n")
    except OSError:
        pass  # fayl yozib bo'lmasa ham, asosiy oqim to'xtamasligi kerak


def last_message_for(phone: str) -> dict | None:
    """Shu raqamga yuborilgan oxirgi xabar (testlar uchun qulaylik)."""
    for msg in reversed(_outbox):
        if msg["phone"] == phone:
            return msg
    return None
