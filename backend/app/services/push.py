"""Optional Firebase Cloud Messaging transport.

The caller's database transaction is authoritative. Delivery failures are
logged and swallowed so a transient push outage cannot roll back an order.
Production should inject and rotate a short-lived OAuth access token via a
secret manager (or replace this adapter with the deployment's credential flow).
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("push")


def send_push(token: str, title: str, body: str, data: dict | None = None) -> bool:
    if not settings.FCM_PROJECT_ID or not settings.FCM_ACCESS_TOKEN:
        return False
    url = f"https://fcm.googleapis.com/v1/projects/{settings.FCM_PROJECT_ID}/messages:send"
    payload = {
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": {str(k): str(v) for k, v in (data or {}).items()},
        }
    }
    try:
        response = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.FCM_ACCESS_TOKEN}"},
            timeout=3.0,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception("FCM delivery failed")
        return False
