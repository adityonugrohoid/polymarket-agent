"""Simulation layer — synthetic 15-minute markets with lagged odds.

Injects fake markets around current Binance prices so the divergence
detector fires within seconds.  Controlled by SIMULATION_MODE config flag.
Fully removable: delete this file + the config branch in agent.py.
"""
import asyncio
import logging
import random
import time
from collections import deque
from typing import Optional

from feeds.binance_ws import BinanceFeed
from feeds.gamma_discovery import DiscoveredMarket
from shared.config import Config
from shared.schemas import OddsSnapshot, PriceTick

logger = logging.getLogger(__name__)

# Fallback prices when Binance hasn't sent data yet
DEFAULT_PRICES = {
    "btcusdt": 87000.0,
    "ethusdt": 2400.0,
    "solusdt": 140.0,
}


class SimulatedMarketGenerator:
    """Generate synthetic 15-minute crypto price markets."""

    def __init__(self, config: Config, binance_feed: BinanceFeed):
        self.config = config
        self.binance_feed = binance_feed

    def generate_markets(self) -> list[DiscoveredMarket]:
        """Create simulated markets at strike levels around current price.

        For each symbol, generates SIM_MARKETS_PER_SYMBOL markets at:
          - current_price * (1 - spread%)
          - current_price
          - current_price * (1 + spread%)
        """
        markets: list[DiscoveredMarket] = []
        spread = self.config.SIM_STRIKE_SPREAD_PCT / 100.0
        symbols = self.config.binance_symbols_list

        for symbol in symbols:
            price = self.binance_feed.get_latest_price(symbol)
            if price is None:
                price = DEFAULT_PRICES.get(symbol, 1000.0)

            n = self.config.SIM_MARKETS_PER_SYMBOL
            if n == 1:
                offsets = [0.0]
            elif n == 2:
                offsets = [-spread, spread]
            else:
                offsets = [-spread, 0.0, spread]
                # For n > 3, add extra levels
                for j in range(3, n):
                    offsets.append(spread * (j - 1))

            for i, offset in enumerate(offsets):
                strike = round(price * (1 + offset), 2)
                ticker = symbol.replace("usdt", "").upper()
                question = f"Will {ticker} be above ${strike:,.2f} in 15 min?"

                markets.append(
                    DiscoveredMarket(
                        condition_id=f"sim-{symbol}-{i}",
                        token_id=f"sim-tok-{symbol}-{i}",
                        question=question,
                        outcome="Yes",
                        symbol=symbol,
                    )
                )

                logger.info(
                    "Sim market created",
                    extra={
                        "symbol": symbol,
                        "strike": strike,
                        "question": question,
                    },
                )

        return markets


def _strike_from_question(question: str) -> Optional[float]:
    """Extract the dollar strike price from a sim market question.

    Expected format: "Will BTC be above $87,000.00 in 15 min?"
    """
    try:
        after_dollar = question.split("$")[1]
        price_str = after_dollar.split(" ")[0].replace(",", "")
        return float(price_str)
    except (IndexError, ValueError):
        return None


class SimulatedOddsFeed:
    """Produces synthetic odds that deliberately lag behind real Binance prices.

    Same interface shape as PolymarketOddsFeed: has start(), stop(), pushes
    OddsSnapshot to odds_queue.
    """

    def __init__(
        self,
        markets: list[DiscoveredMarket],
        out_queue: asyncio.Queue,
        binance_feed: BinanceFeed,
        config: Config,
    ):
        self.markets = markets
        self.out_queue = out_queue
        self.binance_feed = binance_feed
        self.config = config
        self._running = False

        # Price history deques per symbol — used to create lag
        lag_ticks = max(1, int(config.SIM_PRICE_LAG_SECONDS / config.SIM_ODDS_INTERVAL))
        self._price_buffers: dict[str, deque] = {}
        for m in markets:
            if m.symbol not in self._price_buffers:
                self._price_buffers[m.symbol] = deque(maxlen=lag_ticks + 1)

    async def start(self):
        """Emit odds snapshots at SIM_ODDS_INTERVAL."""
        self._running = True
        noise_pct = self.config.SIM_NOISE_PCT / 100.0
        interval = self.config.SIM_ODDS_INTERVAL

        logger.info(
            "Simulated odds feed starting",
            extra={"markets": len(self.markets), "interval": interval},
        )

        while self._running:
            # Record current prices into lag buffers
            for symbol, buf in self._price_buffers.items():
                price = self.binance_feed.get_latest_price(symbol)
                if price is None:
                    # Use default price until Binance connects
                    price = DEFAULT_PRICES.get(symbol)
                if price is not None:
                    buf.append(price)

            for market in self.markets:
                strike = _strike_from_question(market.question)
                if strike is None:
                    continue

                buf = self._price_buffers.get(market.symbol, deque())
                if not buf:
                    continue

                # Use oldest available price (lagged)
                lagged_price = buf[0]

                # Odds calculation
                distance = (lagged_price - strike) / strike
                raw_odds = 0.5 + (distance * 10)
                noise = random.uniform(-noise_pct, noise_pct)
                odds = max(0.05, min(0.95, raw_odds + noise))

                snapshot = OddsSnapshot(
                    condition_id=market.condition_id,
                    token_id=market.token_id,
                    symbol=market.symbol,
                    question=market.question,
                    outcome=market.outcome,
                    midpoint=round(odds, 4),
                )
                await self.out_queue.put(snapshot)

            await asyncio.sleep(interval)

    def stop(self):
        self._running = False


class SimulatedPriceFeed:
    """Random-walk price feed replacing BinanceFeed when network is unavailable.

    Emits PriceTick to price_queue AND populates the real BinanceFeed's
    _price_history so that get_momentum() / get_latest_price() work correctly
    for the divergence detector.
    """

    def __init__(
        self,
        binance_feed: BinanceFeed,
        out_queue: asyncio.Queue,
        config: Config,
    ):
        self.binance_feed = binance_feed
        self.out_queue = out_queue
        self.config = config
        self._running = False
        self._prices: dict[str, float] = {}
        for symbol in config.binance_symbols_list:
            self._prices[symbol] = DEFAULT_PRICES.get(symbol, 1000.0)

    async def start(self):
        """Emit random-walk price ticks every SIM_ODDS_INTERVAL."""
        self._running = True
        interval = self.config.SIM_ODDS_INTERVAL

        logger.info(
            "Simulated price feed starting",
            extra={"symbols": list(self._prices.keys())},
        )

        while self._running:
            for symbol, price in self._prices.items():
                # Random walk: stddev 0.3% per tick with slight drift
                # Over 20 ticks this produces ~1-2% momentum swings
                change_pct = random.gauss(0.03, 0.3)
                price = price * (1 + change_pct / 100)
                self._prices[symbol] = price

                # Inject into BinanceFeed's price history so momentum works
                self.binance_feed._price_history[symbol].append(price)

                tick = PriceTick(
                    symbol=symbol,
                    price=price,
                    volume_24h=1_000_000.0,
                    price_change_pct=change_pct,
                )
                await self.out_queue.put(tick)

            await asyncio.sleep(interval)

    def stop(self):
        self._running = False
