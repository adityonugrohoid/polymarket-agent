"""Track open positions and enforce exposure limits."""
import logging
from typing import Optional

from storage.db import Database

logger = logging.getLogger(__name__)


class PositionTracker:
    """Tracks open positions and enforces risk limits."""

    def __init__(
        self,
        db: Database,
        max_capital: float = 1000.0,
        max_position_size: float = 50.0,
        max_open_positions: int = 3,
    ):
        self.db = db
        self.max_capital = max_capital
        self.max_position_size = max_position_size
        self.max_open_positions = max_open_positions

    async def can_trade(self, size_usd: float) -> tuple[bool, str]:
        """Check if a new trade is allowed under risk limits."""
        open_trades = await self.db.get_open_trades()

        # Check position count
        if len(open_trades) >= self.max_open_positions:
            return False, f"Max open positions reached ({self.max_open_positions})"

        # Check position size
        if size_usd > self.max_position_size:
            return False, f"Size ${size_usd:.0f} exceeds max ${self.max_position_size:.0f}"

        # Check total exposure
        total_exposure = sum(t["size_usd"] for t in open_trades)
        if total_exposure + size_usd > self.max_capital:
            return (
                False,
                f"Total exposure ${total_exposure + size_usd:.0f} exceeds max ${self.max_capital:.0f}",
            )

        return True, "OK"

    async def get_available_capital(self) -> float:
        """Get remaining capital available for new positions."""
        open_trades = await self.db.get_open_trades()
        total_exposure = sum(t["size_usd"] for t in open_trades)
        return max(0.0, self.max_capital - total_exposure)

    async def get_open_count(self) -> int:
        """Get count of open positions."""
        open_trades = await self.db.get_open_trades()
        return len(open_trades)
