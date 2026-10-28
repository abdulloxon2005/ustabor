# Hamma modellar shu yerda import qilinadi: Alembic va SQLAlchemy
# Base.metadata ga ularning hammasi tushganini shu orqali biladi.
from app.models.category import Category
from app.models.master import MasterProfile, MasterService
from app.models.order import Order, OrderOffer, OrderStatusHistory, Quote
from app.models.otp import LoginAttempt, OtpCode
from app.models.payment import Payment
from app.models.review import Review
from app.models.user import User

__all__ = [
    "Category",
    "LoginAttempt",
    "MasterProfile",
    "MasterService",
    "Order",
    "OrderOffer",
    "OrderStatusHistory",
    "OtpCode",
    "Payment",
    "Quote",
    "Review",
    "User",
]