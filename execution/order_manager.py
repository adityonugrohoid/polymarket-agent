"""Real order placement with validation."""
import logging
import uuid
from datetime import datetime

from execution.polymarket_client import PolymarketClient
from execution.position_tracker import PositionTracker
from shared.schemas import (
    CouncilDecision,
    OrderResult,
    OrderSide,
    TradeAction,
    TradeRecord,
)
from storage.db import Database

logger = logging.getLogger(__name__)


class OrderManager:
    """Manages real order placement on Polymarket."""

    def __init__(
        self,
        polymarket_client: PolymarketClient,
        db: Database,
        position_tracker: PositionTracker,
    ):
        self.client = polymarket_client
        self.db = db
        self.position_tracker = position_tracker

    async def execute(self, decision: CouncilDecision) -> OrderResult | None:
        """Execute a real trade based on council decision."""
        if decision.verdict.action != TradeAction.TRADE:
            return None

        size_usd = decision.verdict.size_usd
        signal = decision.signal

        # Check risk limits
        can_trade, reason = await self.position_tracker.can_trade(size_usd)
        if not can_trade:
            logger.warning(
                "Live trade blocked by risk limits",
                extra={"reason": reason, "size_usd": size_usd},
            )
            return None

        # Determine side
        side = "BUY" if signal.direction == "UP" else "SELL"
        side_enum = OrderSide.BUY if side == "BUY" else OrderSide.SELL

        # Get current midpoint for fill price
        midpoint = self.client.get_midpoint(signal.token_id)
        if midpoint is None or midpoint <= 0:
            logger.error("Cannot get midpoint for live trade")
            return None

        # Calculate number of shares
        num_shares = size_usd / midpoint

        # Post order
        resp = self.client.create_and_post_order(
            token_id=signal.token_id,
            price=midpoint,
            size=num_shares,
            side=side,
        )

        if resp is None:
            logger.error("Live order failed")
            return None

        order_id = resp.get("orderID", f"live-{uuid.uuid4().hex[:12]}")

        order = OrderResult(
            order_id=order_id,
            condition_id=signal.condition_id,
            token_id=signal.token_id,
            symbol=signal.symbol,
            side=side_enum,
            size_usd=size_usd,
            price=midpoint,
            filled=True,
            is_paper=False,
        )

        # Log to database
        record = TradeRecord(
            order_id=order_id,
            symbol=signal.symbol,
            condition_id=signal.condition_id,
            token_id=signal.token_id,
            side=side,
            size_usd=size_usd,
            entry_price=midpoint,
            is_paper=False,
            signal_score=signal.signal_score,
            sentiment=decision.sentiment.sentiment.value,
            confidence=decision.confidence.confidence,
            verdict=decision.verdict.action.value,
            council_reasoning=decision.verdict.reasoning[:500],
        )
        trade_id = await self.db.log_trade(record)

        logger.info(
            "LIVE trade executed",
            extra={
                "order_id": order_id,
                "trade_id": trade_id,
                "symbol": signal.symbol,
                "side": side,
                "size_usd": size_usd,
                "price": midpoint,
            },
        )

        return order
