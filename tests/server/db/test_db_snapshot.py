"""Snapshot test for verifying fixture database schema and content integrity using Syrupy."""

import sqlite3
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"
SQLITE_FIXTURES = sorted(FIXTURES_DIR.glob("*.sqlite"))


def generate_sql_dump(db_path: Path) -> str:
    """Generate a deterministic SQL dump from a SQLite database file."""
    conn = sqlite3.connect(db_path)
    lines = list(conn.iterdump())
    conn.close()
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("db_path", SQLITE_FIXTURES, ids=lambda p: p.name)
def test_sqlite_fixture_matches_snapshot(db_path: Path, snapshot) -> None:
    """Verify that all fixture SQLite databases match their golden Syrupy snapshots."""
    assert db_path.exists(), f"Fixture database not found at {db_path}"
    actual_dump = generate_sql_dump(db_path)
    assert actual_dump == snapshot(name=f"{db_path.stem}_sql_dump")
