"""Paper trading: simulate fills and log to database."""
import logging
import uuid
from datetime import datetime

from execution.position_tracker import PositionTracker
from shared.schemas import (
    CouncilDecision,
    OrderResult,
    OrderSide,
    TradeRecord,
    TradeAction,
)
from storage.db import Database

logger = logging.getLogger(__name__)


class PaperTrader:
    """Simulates trade execution without real money."""

    def __init__(self, db: Database, position_tracker: PositionTracker):
        self.db = db
        self.position_tracker = position_tracker

    async def execute(self, decision: CouncilDecision) -> OrderResult | None:
        """Execute a paper trade based on council decision."""
        if decision.verdict.action != TradeAction.TRADE:
            return None

        size_usd = decision.verdict.size_usd
        signal = decision.signal

        # Check risk limits
        can_trade, reason = await self.position_tracker.can_trade(size_usd)
        if not can_trade:
            logger.warning(
                "Paper trade blocked by risk limits",
                extra={"reason": reason, "size_usd": size_usd},
            )
            return None

        # Determine side based on direction
        side = OrderSide.BUY if signal.direction == "UP" else OrderSide.SELL
        order_id = f"paper-{uuid.uuid4().hex[:12]}"

        # Simulate fill at current midpoint
        fill_price = signal.odds_midpoint

        order = OrderResult(
            order_id=order_id,
            condition_id=signal.condition_id,
            token_id=signal.token_id,
            symbol=signal.symbol,
            side=side,
            size_usd=size_usd,
            price=fill_price,
            filled=True,
            is_paper=True,
        )

        # Log to database
        record = TradeRecord(
            order_id=order_id,
            symbol=signal.symbol,
            condition_id=signal.condition_id,
            token_id=signal.token_id,
            side=side.value,
            size_usd=size_usd,
            entry_price=fill_price,
            is_paper=True,
            signal_score=signal.signal_score,
            sentiment=decision.sentiment.sentiment.value,
            confidence=decision.confidence.confidence,
            verdict=decision.verdict.action.value,
            council_reasoning=decision.verdict.reasoning[:500],
        )
        trade_id = await self.db.log_trade(record)

        logger.info(
            "Paper trade executed",
            extra={
                "order_id": order_id,
                "trade_id": trade_id,
                "symbol": signal.symbol,
                "side": side.value,
                "size_usd": size_usd,
                "price": fill_price,
            },
        )

        # Log signal
        await self.db.log_signal({
            "symbol": signal.symbol,
            "price": signal.price,
            "momentum_pct": signal.price_momentum_pct,
            "odds_midpoint": signal.odds_midpoint,
            "implied_fair_odds": signal.implied_fair_odds,
            "edge_pct": signal.edge_pct,
            "signal_score": signal.signal_score,
            "direction": signal.direction,
            "council_action": "TRADE",
        })

        return order
