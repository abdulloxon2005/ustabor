from contextlib import closing
import re
import sqlite3

import pytest

from scripts.backup_db import backup_database


def test_backup_sqlite_database_creates_valid_copy(tmp_path, capsys):
    src_db = tmp_path / "source.db"
    with closing(sqlite3.connect(src_db)) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO sample (name) VALUES ('UstaBor')")
        conn.commit()

    backups_dir = tmp_path / "backups"
    dest_path = backup_database(
        database_url=f"sqlite:///{src_db.as_posix()}",
        backup_dir=backups_dir,
    )

    captured = capsys.readouterr().out.strip()
    assert captured == str(dest_path)
    assert dest_path.is_file()
    assert re.fullmatch(r"ustabor_\d{8}_\d{6}\.db", dest_path.name)

    with closing(sqlite3.connect(dest_path)) as bconn:
        row = bconn.execute("SELECT id, name FROM sample").fetchone()
        assert row == (1, "UstaBor")


def test_backup_rejects_non_sqlite_url(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        backup_database(
            database_url="postgresql+psycopg://user:pass@localhost:5432/ustabor",
            backup_dir=tmp_path / "backups",
        )
    msg = str(exc_info.value)
    assert "SQLite" in msg
    assert "Xatolik" in msg
