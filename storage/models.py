"""SQLite table definitions."""

CREATE_TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    condition_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    side TEXT NOT NULL,
    size_usd REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    pnl REAL,
    is_paper INTEGER NOT NULL DEFAULT 1,
    signal_score REAL DEFAULT 0,
    sentiment TEXT DEFAULT '',
    confidence REAL DEFAULT 0,
    verdict TEXT DEFAULT '',
    council_reasoning TEXT DEFAULT '',
    opened_at TEXT NOT NULL,
    closed_at TEXT
);
"""

CREATE_SIGNALS_TABLE = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    price REAL NOT NULL,
    momentum_pct REAL NOT NULL,
    odds_midpoint REAL NOT NULL,
    implied_fair_odds REAL NOT NULL,
    edge_pct REAL NOT NULL,
    signal_score REAL NOT NULL,
    direction TEXT NOT NULL,
    council_action TEXT DEFAULT 'SKIP',
    timestamp TEXT NOT NULL
);
"""
