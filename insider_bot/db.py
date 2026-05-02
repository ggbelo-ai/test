"""SQLite schema and helpers."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    accession        TEXT NOT NULL,
    ticker           TEXT NOT NULL,
    cik              TEXT NOT NULL,
    owner_cik        TEXT,
    owner_name       TEXT,
    owner_title      TEXT,
    is_director      INTEGER,
    is_officer       INTEGER,
    is_ten_percent   INTEGER,
    transaction_date TEXT NOT NULL,
    filing_date      TEXT NOT NULL,
    code             TEXT NOT NULL,
    shares           REAL,
    price            REAL,
    value            REAL,
    PRIMARY KEY (accession, owner_name, transaction_date, code, shares, price)
);
CREATE INDEX IF NOT EXISTS idx_tx_ticker_date
    ON transactions (ticker, transaction_date);
CREATE INDEX IF NOT EXISTS idx_tx_filing
    ON transactions (filing_date);

CREATE TABLE IF NOT EXISTS prices (
    ticker  TEXT NOT NULL,
    date    TEXT NOT NULL,
    open    REAL,
    high    REAL,
    low     REAL,
    close   REAL,
    volume  REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS paper_positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    entry_date      TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    notional        REAL NOT NULL,
    shares          REAL NOT NULL,
    confidence      REAL NOT NULL,
    insider_count   INTEGER NOT NULL,
    purchase_value  REAL NOT NULL,
    last_price      REAL,
    last_marked     TEXT,
    rationale       TEXT,
    closed          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pos_ticker_open
    ON paper_positions (ticker, closed);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def set_meta(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_meta(key: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
