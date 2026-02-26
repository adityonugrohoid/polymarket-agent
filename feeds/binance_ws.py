"""Binance WebSocket price feeds with rolling momentum calculation."""
import asyncio
import logging
import time
from collections import deque
from typing import Optional

from binance import AsyncClient, BinanceSocketManager

from shared.schemas import PriceTick

logger = logging.getLogger(__name__)

# Rolling window for momentum calculation (last N ticks)
MOMENTUM_WINDOW = 20


class BinanceFeed:
    """Streams real-time price ticks from Binance WebSocket."""

    def __init__(self, symbols: list[str], out_queue: asyncio.Queue):
        self.symbols = [s.lower() for s in symbols]
        self.out_queue = out_queue
        self._price_history: dict[str, deque] = {
            s: deque(maxlen=MOMENTUM_WINDOW) for s in self.symbols
        }
        self._running = False

    def _calc_momentum(self, symbol: str, current_price: float) -> float:
        """Calculate price momentum as % change over rolling window."""
        history = self._price_history[symbol]
        if len(history) < 2:
            return 0.0
        oldest = history[0]
        if oldest == 0:
            return 0.0
        return ((current_price - oldest) / oldest) * 100.0

    async def start(self):
        """Connect to Binance and stream ticker data."""
        self._running = True
        client = await AsyncClient.create()
        bm = BinanceSocketManager(client)

        streams = [f"{s}@ticker" for s in self.symbols]
        ms = bm.multiplex_socket(streams)

        logger.info("Binance WS connecting", extra={"symbols": self.symbols})

        async with ms as stream:
            while self._running:
                try:
                    msg = await asyncio.wait_for(stream.recv(), timeout=30.0)
                except asyncio.TimeoutError:
                    logger.warning("Binance WS timeout, reconnecting")
                    continue

                if msg.get("e") == "error":
                    logger.error("Binance WS error", extra={"msg": msg})
                    continue

                data = msg.get("data", msg)
                if "s" not in data:
                    continue

                symbol = data["s"].lower()
                price = float(data.get("c", 0))
                volume = float(data.get("v", 0))
                change_pct = float(data.get("P", 0))

                self._price_history[symbol].append(price)
                momentum = self._calc_momentum(symbol, price)

                tick = PriceTick(
                    symbol=symbol,
                    price=price,
                    volume_24h=volume,
                    price_change_pct=change_pct,
                )

                await self.out_queue.put(tick)
                logger.debug(
                    "Price tick",
                    extra={
                        "symbol": symbol,
                        "price": price,
                        "momentum": round(momentum, 4),
                    },
                )

        await client.close_connection()

    def stop(self):
        self._running = False

    def get_momentum(self, symbol: str) -> float:
        """Get current momentum for a symbol."""
        symbol = symbol.lower()
        history = self._price_history.get(symbol, deque())
        if len(history) < 2:
            return 0.0
        oldest = history[0]
        newest = history[-1]
        if oldest == 0:
            return 0.0
        return ((newest - oldest) / oldest) * 100.0

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get the most recent price for a symbol."""
        symbol = symbol.lower()
        history = self._price_history.get(symbol, deque())
        return history[-1] if history else None
