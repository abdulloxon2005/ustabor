import enum

from sqlalchemy import Enum as SAEnum


class Role(str, enum.Enum):
    CUSTOMER = "customer"
    MASTER = "master"
    ADMIN = "admin"


class OrderStatus(str, enum.Enum):
    SEARCHING = "searching"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PricingType(str, enum.Enum):
    FIXED = "fixed"   # qat'iy narx (base_price)
    QUOTE = "quote"   # usta narx taklif qiladi


class SelectionMode(str, enum.Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"


class OfferStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class QuoteStatus(str, enum.Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class PaymentMethod(str, enum.Enum):
    CASH = "cash"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"


def enum_type(enum_cls: type[enum.Enum]) -> SAEnum:
    """Enumni bazada VARCHAR sifatida saqlaydi (SQLite va PostgreSQL uchun bir xil).

    values_callable: bazaga nom (CUSTOMER) emas, qiymat ("customer") yoziladi.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=20,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
        name=enum_cls.__name__.lower(),
    )