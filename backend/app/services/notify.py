"""Bildirishnoma: ilova ichi (Notification) + SMS (mock, app/services/sms.py).

COMMIT QILMAYDI — chaqiruvchi funksiya/endpoint o'z amali bilan birga commit qiladi
(order_flow/pricing/matching qoidasi bilan bir xil).
"""

from sqlalchemy.orm import Session

from app.models import Notification, User
from app.services import sms


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
    if user is not None and user.phone:
        sms.send_sms(user.phone, f"{title}: {body}")

    return notification
