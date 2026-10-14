"""Har bir jadvalda nechta yozuv borligini ko'rsatadi.

Ishga tushirish:  python -m scripts.check_db
"""

from sqlalchemy import func, select

from app.db.base import Base
from app.db.session import SessionLocal
import app.models  # noqa: F401


def main() -> None:
    with SessionLocal() as db:
        for table in Base.metadata.sorted_tables:
            count = db.scalar(select(func.count()).select_from(table))
            print(f"{table.name:25} {count}")


if __name__ == "__main__":
    main()