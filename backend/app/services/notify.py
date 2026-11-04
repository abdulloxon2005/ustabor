"""Bildirishnoma: ilova ichi (Notification) + SMS (mock, app/services/sms.py).

COMMIT QILMAYDI — chaqiruvchi funksiya/endpoint o'z amali bilan birga commit qiladi
(order_flow/pricing/matching qoidasi bilan bir xil).
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DeviceToken, Notification, User
from app.services import push, sms

logger = logging.getLogger("notifications")

# SMS pullik va bezovta qiladi: faqat darhol harakat talab qiladigan hodisalar uchun.
# Qolganlari ilova ichi bildirishnoma va push orqali boradi.
SMS_NOTIFICATION_TYPES = frozenset({
    "new_offer",
    "order_assigned",
    "order_completed",
    "order_cancelled",
    "master_approved",
})


def notify_user(
    db: Session,
    user_id: int,
    type: str,
    title: str,
    body: str,
    order_id: int | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        related_order_id=order_id,
    )
    db.add(notification)
    db.flush()

    user = db.get(User, user_id)
    if user is not None and user.phone and type in SMS_NOTIFICATION_TYPES:
        sms.send_sms(user.phone, f"{title}: {body}")

    if user is not None:
        tokens = db.scalars(
            select(DeviceToken).where(
                DeviceToken.user_id == user_id, DeviceToken.is_active.is_(True)
            )
        ).all()
        for device in tokens:
            try:
                push.send_push(device.token, title, body, {"type": type, "order_id": order_id or ""})
            except Exception:
                # Push is best-effort and must never roll back the core action.
                logger.exception("Push delivery adapter failed")

    return notification
