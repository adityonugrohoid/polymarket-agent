"""Core algorithm: detect divergence between exchange price momentum and Polymarket odds."""
import asyncio
import logging
from typing import Optional

from feeds.binance_ws import BinanceFeed
from feeds.feed_aggregator import PairedData
from shared.schemas import DivergenceSignal
from strategy.signal import composite_score
from strategy.thresholds import MIN_EDGE_PCT, MIN_SIGNAL_SCORE, MIN_MOMENTUM_PCT

logger = logging.getLogger(__name__)


def compute_implied_odds(
    current_odds: float,
    momentum_pct: float,
) -> float:
    """Estimate what the odds SHOULD be given price momentum.

    Simple model: if BTC is surging +2%, the odds of "BTC above X" should be
    higher than what the market currently shows (if the market is stale).

    Returns adjusted odds clamped to [0.01, 0.99].
    """
    # Scale factor: 1% price move ≈ 3% odds adjustment (tunable)
    adjustment = momentum_pct * 0.03
    implied = current_odds + adjustment
    return max(0.01, min(0.99, implied))


class DivergenceDetector:
    """Consumes paired price+odds data and emits DivergenceSignal when edge is found."""

    def __init__(
        self,
        paired_queue: asyncio.Queue,
        signal_queue: asyncio.Queue,
        binance_feed: BinanceFeed,
        min_edge_pct: float = MIN_EDGE_PCT,
        min_signal_score: float = MIN_SIGNAL_SCORE,
    ):
        self.paired_queue = paired_queue
        self.signal_queue = signal_queue
        self.binance_feed = binance_feed
        self.min_edge_pct = min_edge_pct
        self.min_signal_score = min_signal_score
        self._running = False

    async def start(self):
        """Consume paired data and emit divergence signals."""
        self._running = True
        logger.info("Divergence detector started")

        while self._running:
            try:
                paired: PairedData = await asyncio.wait_for(
                    self.paired_queue.get(), timeout=5.0
                )
            except asyncio.TimeoutError:
                continue

            signal = self._evaluate(paired)
            if signal:
                await self.signal_queue.put(signal)
                logger.info(
                    "Divergence signal",
                    extra={
                        "symbol": signal.symbol,
                        "edge_pct": signal.edge_pct,
                        "score": signal.signal_score,
                        "direction": signal.direction,
                    },
                )

    def _evaluate(self, paired: PairedData) -> Optional[DivergenceSignal]:
        """Evaluate a paired tick+odds for divergence."""
        tick = paired.tick
        odds = paired.odds

        # Get momentum from Binance feed's rolling window
        momentum = self.binance_feed.get_momentum(tick.symbol)

        # Skip if momentum is negligible
        if abs(momentum) < MIN_MOMENTUM_PCT:
            return None

        # Compute what odds should be given price momentum
        implied = compute_implied_odds(odds.midpoint, momentum)

        # Edge = difference between implied fair odds and current market odds
        edge_pct = (implied - odds.midpoint) * 100.0

        # Skip if edge is below threshold
        if abs(edge_pct) < self.min_edge_pct:
            return None

        # Compute composite signal score
        score = composite_score(
            edge_pct=edge_pct,
            momentum_pct=momentum,
            volume_24h=tick.volume_24h,
        )

        # Skip if score is below threshold
        if score < self.min_signal_score:
            return None

        direction = "UP" if momentum > 0 else "DOWN"

        return DivergenceSignal(
            symbol=tick.symbol,
            price=tick.price,
            price_momentum_pct=momentum,
            odds_midpoint=odds.midpoint,
            implied_fair_odds=implied,
            edge_pct=edge_pct,
            signal_score=score,
            direction=direction,
            condition_id=odds.condition_id,
            token_id=odds.token_id,
        )

    def stop(self):
        self._running = False
