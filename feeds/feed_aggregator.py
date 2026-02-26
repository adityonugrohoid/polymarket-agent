"""Merge price ticks and odds snapshots into paired signals."""
import asyncio
import logging
from typing import Optional

from feeds.gamma_discovery import DiscoveredMarket
from shared.schemas import PriceTick, OddsSnapshot

logger = logging.getLogger(__name__)


class PairedData:
    """A price tick paired with the latest odds for the same symbol."""

    def __init__(self, tick: PriceTick, odds: OddsSnapshot):
        self.tick = tick
        self.odds = odds


class FeedAggregator:
    """Consumes price and odds queues, pairs by symbol, emits to signal queue."""

    def __init__(
        self,
        price_queue: asyncio.Queue,
        odds_queue: asyncio.Queue,
        signal_queue: asyncio.Queue,
        markets: list[DiscoveredMarket],
    ):
        self.price_queue = price_queue
        self.odds_queue = odds_queue
        self.signal_queue = signal_queue
        self._latest_odds: dict[str, OddsSnapshot] = {}
        self._symbol_to_markets: dict[str, list[DiscoveredMarket]] = {}
        self._running = False

        # Index markets by symbol
        for m in markets:
            self._symbol_to_markets.setdefault(m.symbol, []).append(m)

    async def start(self):
        """Run both consumers concurrently."""
        self._running = True
        await asyncio.gather(
            self._consume_odds(),
            self._consume_prices(),
        )

    async def _consume_odds(self):
        """Update latest odds cache from odds queue."""
        while self._running:
            try:
                odds: OddsSnapshot = await asyncio.wait_for(
                    self.odds_queue.get(), timeout=5.0
                )
                self._latest_odds[odds.token_id] = odds
            except asyncio.TimeoutError:
                continue

    async def _consume_prices(self):
        """Pair price ticks with latest odds and emit."""
        while self._running:
            try:
                tick: PriceTick = await asyncio.wait_for(
                    self.price_queue.get(), timeout=5.0
                )
            except asyncio.TimeoutError:
                continue

            # Find markets for this symbol
            markets = self._symbol_to_markets.get(tick.symbol, [])
            for market in markets:
                odds = self._latest_odds.get(market.token_id)
                if odds is None:
                    continue

                paired = PairedData(tick=tick, odds=odds)
                await self.signal_queue.put(paired)

                logger.debug(
                    "Paired signal",
                    extra={
                        "symbol": tick.symbol,
                        "price": tick.price,
                        "midpoint": odds.midpoint,
                    },
                )

    def stop(self):
        self._running = False
