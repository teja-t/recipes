"""SQLite-backed dedup store for seen listings.

A listing is uniquely identified by (source, listing_id). `mark_seen` is
the only write path; it returns True the first time a listing is recorded
and False on every subsequent call, so callers can use it as the dedup
gate before sending an alert.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_listings (
    source      TEXT NOT NULL,
    listing_id  TEXT NOT NULL,
    title       TEXT,
    url         TEXT,
    first_seen  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (source, listing_id)
);
"""


@contextmanager
def _connect(path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path: Path = DB_PATH) -> None:
    with _connect(path) as conn:
        conn.executescript(SCHEMA)


def mark_seen(source: str, listing_id: str, title: str = "", url: str = "") -> bool:
    """Insert a listing. Returns True if newly inserted, False if already seen."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO seen_listings (source, listing_id, title, url) "
            "VALUES (?, ?, ?, ?)",
            (source, str(listing_id), title, url),
        )
        return cur.rowcount == 1


def is_seen(source: str, listing_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT 1 FROM seen_listings WHERE source = ? AND listing_id = ?",
            (source, str(listing_id)),
        )
        return cur.fetchone() is not None


def count(source: str | None = None) -> int:
    with _connect() as conn:
        if source is None:
            cur = conn.execute("SELECT COUNT(*) FROM seen_listings")
        else:
            cur = conn.execute(
                "SELECT COUNT(*) FROM seen_listings WHERE source = ?", (source,)
            )
        return cur.fetchone()[0]
