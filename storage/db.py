"""SQLite database via aiosqlite."""
import aiosqlite
import logging
import os
from datetime import datetime
from typing import Optional

from shared.schemas import TradeRecord
from storage.models import CREATE_TRADES_TABLE, CREATE_SIGNALS_TABLE

logger = logging.getLogger(__name__)


class Database:
    """Async SQLite database for trade records."""

    def __init__(self, db_path: str = "data/trades.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self):
        """Initialize database and create tables."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute(CREATE_TRADES_TABLE)
        await self._db.execute(CREATE_SIGNALS_TABLE)
        await self._db.commit()
        logger.info("Database initialized", extra={"path": self.db_path})

    async def close(self):
        if self._db:
            await self._db.close()

    async def log_trade(self, record: TradeRecord) -> int:
        """Insert a trade record and return its ID."""
        cursor = await self._db.execute(
            """INSERT INTO trades
               (order_id, symbol, condition_id, token_id, side, size_usd,
                entry_price, exit_price, pnl, is_paper, signal_score,
                sentiment, confidence, verdict, council_reasoning,
                opened_at, closed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.order_id, record.symbol, record.condition_id,
                record.token_id, record.side, record.size_usd,
                record.entry_price, record.exit_price, record.pnl,
                1 if record.is_paper else 0, record.signal_score,
                record.sentiment, record.confidence, record.verdict,
                record.council_reasoning,
                record.opened_at.isoformat(),
                record.closed_at.isoformat() if record.closed_at else None,
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def close_trade(self, order_id: str, exit_price: float, pnl: float):
        """Close a trade by updating exit price and PnL."""
        now = datetime.utcnow().isoformat()
        await self._db.execute(
            """UPDATE trades SET exit_price=?, pnl=?, closed_at=?
               WHERE order_id=? AND closed_at IS NULL""",
            (exit_price, pnl, now, order_id),
        )
        await self._db.commit()

    async def get_open_trades(self) -> list[dict]:
        """Get all open (unclosed) trades."""
        cursor = await self._db.execute(
            "SELECT * FROM trades WHERE closed_at IS NULL ORDER BY opened_at DESC"
        )
        rows = await cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    async def get_recent_trades(self, limit: int = 50) -> list[dict]:
        """Get recent trades."""
        cursor = await self._db.execute(
            "SELECT * FROM trades ORDER BY opened_at DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    async def get_pnl_summary(self) -> dict:
        """Get aggregate P&L summary."""
        cursor = await self._db.execute(
            """SELECT
                 COUNT(*) as total_trades,
                 SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                 SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                 SUM(CASE WHEN pnl IS NULL THEN 1 ELSE 0 END) as open,
                 COALESCE(SUM(pnl), 0) as total_pnl,
                 COALESCE(AVG(pnl), 0) as avg_pnl,
                 COALESCE(SUM(size_usd), 0) as total_volume
               FROM trades"""
        )
        row = await cursor.fetchone()
        columns = [d[0] for d in cursor.description]
        result = dict(zip(columns, row))
        total = result["wins"] + result["losses"]
        result["win_rate"] = (result["wins"] / total * 100) if total > 0 else 0
        return result

    async def log_signal(self, signal_data: dict):
        """Log a divergence signal."""
        await self._db.execute(
            """INSERT INTO signals
               (symbol, price, momentum_pct, odds_midpoint, implied_fair_odds,
                edge_pct, signal_score, direction, council_action, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal_data["symbol"], signal_data["price"],
                signal_data["momentum_pct"], signal_data["odds_midpoint"],
                signal_data["implied_fair_odds"], signal_data["edge_pct"],
                signal_data["signal_score"], signal_data["direction"],
                signal_data.get("council_action", "SKIP"),
                signal_data.get("timestamp", datetime.utcnow().isoformat()),
            ),
        )
        await self._db.commit()
