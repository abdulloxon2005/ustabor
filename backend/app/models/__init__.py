# Hamma modellar shu yerda import qilinadi: Alembic va SQLAlchemy
# Base.metadata ga ularning hammasi tushganini shu orqali biladi.
from app.models.audit_log import AdminAuditLog
from app.models.availability import MasterAvailability
from app.models.category import Category
from app.models.dispute import Dispute
from app.models.chat_report import ChatReport
from app.models.device_token import DeviceToken
from app.models.favorite import Favorite
from app.models.master import MasterProfile, MasterService
from app.models.message import OrderMessage
from app.models.notification import Notification
from app.models.order import Order, OrderOffer, OrderStatusHistory, Quote
from app.models.otp import LoginAttempt, OtpCode
from app.models.payment import Payment
from app.models.platform_setting import PlatformSetting
from app.models.photo import MasterPhoto, OrderPhoto
from app.models.review import Review
from app.models.user import User

__all__ = [
    "AdminAuditLog",
    "Category",
    "ChatReport",
    "Dispute",
    "DeviceToken",
    "Favorite",
    "LoginAttempt",
    "MasterAvailability",
    "MasterPhoto",
    "MasterProfile",
    "MasterService",
    "Notification",
    "Order",
    "OrderMessage",
    "OrderOffer",
    "OrderPhoto",
    "OrderStatusHistory",
    "OtpCode",
    "Payment",
    "PlatformSetting",
    "Quote",
    "Review",
    "User",
]
