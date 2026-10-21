"""SQLite ma'lumotlar bazasidan xavfsiz zaxira nusxa (backup) olish skripti.

Ishga tushirish (backend papkasidan):  python -m scripts.backup_db
"""

from contextlib import closing
from datetime import datetime
import os
from pathlib import Path
import sqlite3

from sqlalchemy.engine import make_url

from app.core.config import settings

NON_SQLITE_ERROR = (
    "Xatolik: Zaxira nusxa faqat SQLite ma'lumotlar bazasi uchun "
    "qo'llab-quvvatlanadi (DATABASE_URL 'sqlite:///' bilan boshlanishi kerak)."
)


def backup_database(
    database_url: str | None = None,
    backup_dir: str | Path = "backups",
) -> Path:
    raw_url = (database_url if database_url is not None else (os.environ.get("DATABASE_URL") or settings.DATABASE_URL)).strip()
    try:
        url = make_url(raw_url)
    except Exception:
        raise SystemExit(NON_SQLITE_ERROR)

    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise SystemExit(NON_SQLITE_ERROR)

    src_path = Path(url.database)
    if not src_path.is_file():
        raise SystemExit(f"Xatolik: Ma'lumotlar bazasi fayli topilmadi: {src_path}")

    out_dir = Path(backup_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_path = out_dir / f"ustabor_{timestamp}.db"

    with closing(sqlite3.connect(src_path)) as src_conn, closing(
        sqlite3.connect(dest_path)
    ) as dst_conn:
        src_conn.backup(dst_conn)

    print(dest_path)
    return dest_path


def main() -> None:
    backup_database()


if __name__ == "__main__":
    main()
