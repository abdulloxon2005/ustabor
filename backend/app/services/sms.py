"""SMS yuborish xizmati вЂ” HOZIRCHA MOCK.

Haqiqiy SMS yuborilmaydi: xabar log'ga yoziladi va (faqat testlar/debug
uchun) xotiradagi _outbox ro'yxatiga qo'shiladi.

PRODUCTIONGA CHIQISHDAN OLDIN: send_sms() funksiyasini haqiqiy provayderga
(masalan Eskiz.uz, Play Mobile) ulash kerak вЂ” qolgan kod (otp.py, notify.py)
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
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    _outbox.append({"phone": phone, "text": text, "created_at": ts})
    if len(_outbox) > _OUTBOX_LIMIT:
        del _outbox[: len(_outbox) - _OUTBOX_LIMIT]
    try:
        with open(_OUTBOX_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {phone}: {text}\n")
    except OSError:
        pass  # fayl yozib bo'lmasa ham, asosiy oqim to'xtamasligi kerak


def last_message_for(phone: str) -> dict | None:
    """Shu raqamga yuborilgan oxirgi xabar (testlar uchun qulaylik)."""
    for msg in reversed(_outbox):
        if msg["phone"] == phone:
            return msg
    return None


def recent_messages(limit: int = 50) -> list[dict]:
    """Mock SMS fayldan oxirgi xabarlarni o'qiydi (eng yangisi birinchi).

    Fayl mavjud bo'lmasa yoki diskka yozish imkoni bo'lmasa (masalan ba'zi
    server / konteyner muhitlarida), xotiradagi _outbox ro'yxatidan olinadi.
    """
    items: list[dict] = []
    try:
        if _OUTBOX_FILE.exists():
            lines = _OUTBOX_FILE.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines):
                # Format: [YYYY-MM-DD HH:MM:SS] +998901234567: matn
                if not line.startswith("[") or "] " not in line:
                    continue
                ts, rest = line[1:].split("] ", 1)
                phone, _, text = rest.partition(": ")
                code = next((w for w in text.replace(".", " ").split() if w.isdigit() and len(w) == 6), None)
                items.append({"created_at": ts, "phone": phone, "text": text, "code": code})
                if len(items) >= limit:
                    return items
    except OSError:
        pass

    if not items and _outbox:
        for m in reversed(_outbox):
            phone = m.get("phone", "")
            text = m.get("text", "")
            ts = m.get("created_at") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            code = next((w for w in text.replace(".", " ").split() if w.isdigit() and len(w) == 6), None)
            items.append({"created_at": ts, "phone": phone, "text": text, "code": code})
            if len(items) >= limit:
                break
    return items
