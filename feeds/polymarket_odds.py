"""Polymarket CLOB odds polling."""
import asyncio
import logging
from typing import Optional

import httpx

from feeds.gamma_discovery import DiscoveredMarket
from shared.schemas import OddsSnapshot

logger = logging.getLogger(__name__)

CLOB_BASE = "https://clob.polymarket.com"


class PolymarketOddsFeed:
    """Polls Polymarket CLOB for midpoint odds."""

    def __init__(
        self,
        markets: list[DiscoveredMarket],
        out_queue: asyncio.Queue,
        poll_interval: float = 5.0,
    ):
        self.markets = markets
        self.out_queue = out_queue
        self.poll_interval = poll_interval
        self._running = False
        self._latest: dict[str, OddsSnapshot] = {}

    async def start(self):
        """Poll CLOB midpoints in a loop."""
        self._running = True
        logger.info(
            "Polymarket odds feed starting",
            extra={"markets": len(self.markets)},
        )

        while self._running:
            for market in self.markets:
                try:
                    snapshot = await self._fetch_midpoint(market)
                    if snapshot:
                        self._latest[market.token_id] = snapshot
                        await self.out_queue.put(snapshot)
                except Exception as e:
                    logger.warning(
                        f"CLOB fetch error: {e}",
                        extra={"token_id": market.token_id},
                    )

            await asyncio.sleep(self.poll_interval)

    async def _fetch_midpoint(self, market: DiscoveredMarket) -> Optional[OddsSnapshot]:
        """Fetch midpoint for a single market."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{CLOB_BASE}/midpoint",
                params={"token_id": market.token_id},
            )
            resp.raise_for_status()
            data = resp.json()

            mid = float(data.get("mid", 0))
            if mid <= 0:
                return None

            return OddsSnapshot(
                condition_id=market.condition_id,
                token_id=market.token_id,
                symbol=market.symbol,
                question=market.question,
                outcome=market.outcome,
                midpoint=mid,
            )

    def stop(self):
        self._running = False

    def get_latest(self, token_id: str) -> Optional[OddsSnapshot]:
        return self._latest.get(token_id)
