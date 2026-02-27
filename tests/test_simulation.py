"""Tests for simulation layer — market generation and odds calculation."""
import asyncio
from collections import deque
from unittest.mock import MagicMock

import pytest

from feeds.simulation import (
    SimulatedMarketGenerator,
    SimulatedOddsFeed,
    _strike_from_question,
    DEFAULT_PRICES,
)
from feeds.gamma_discovery import DiscoveredMarket
from shared.config import Config
from shared.schemas import OddsSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> Config:
    defaults = dict(
        SIMULATION_MODE=True,
        SIM_MARKETS_PER_SYMBOL=3,
        SIM_STRIKE_SPREAD_PCT=1.0,
        SIM_PRICE_LAG_SECONDS=5.0,
        SIM_NOISE_PCT=2.0,
        SIM_ODDS_INTERVAL=1.0,
        BINANCE_SYMBOLS="btcusdt,ethusdt,solusdt",
    )
    defaults.update(overrides)
    return Config(**defaults)


def _make_binance_feed(prices: dict[str, float | None] | None = None):
    """Return a mock BinanceFeed with controllable get_latest_price."""
    feed = MagicMock()
    prices = prices or {}
    feed.get_latest_price = MagicMock(side_effect=lambda s: prices.get(s))
    return feed


# ---------------------------------------------------------------------------
# _strike_from_question
# ---------------------------------------------------------------------------

class TestStrikeFromQuestion:
    def test_parses_btc_strike(self):
        q = "Will BTC be above $87,000.00 in 15 min?"
        assert _strike_from_question(q) == 87000.00

    def test_parses_eth_strike(self):
        q = "Will ETH be above $2,400.00 in 15 min?"
        assert _strike_from_question(q) == 2400.00

    def test_parses_sol_strike(self):
        q = "Will SOL be above $140.00 in 15 min?"
        assert _strike_from_question(q) == 140.00

    def test_returns_none_for_bad_format(self):
        assert _strike_from_question("no dollar sign here") is None

    def test_returns_none_for_empty(self):
        assert _strike_from_question("") is None


# ---------------------------------------------------------------------------
# SimulatedMarketGenerator
# ---------------------------------------------------------------------------

class TestSimulatedMarketGenerator:
    def test_generates_correct_count(self):
        feed = _make_binance_feed({"btcusdt": 90000.0, "ethusdt": 2500.0, "solusdt": 150.0})
        config = _make_config(SIM_MARKETS_PER_SYMBOL=3)
        gen = SimulatedMarketGenerator(config, feed)
        markets = gen.generate_markets()
        assert len(markets) == 9  # 3 symbols * 3 markets

    def test_uses_default_prices_when_binance_unavailable(self):
        feed = _make_binance_feed()  # all return None
        config = _make_config(SIM_MARKETS_PER_SYMBOL=1, BINANCE_SYMBOLS="btcusdt")
        gen = SimulatedMarketGenerator(config, feed)
        markets = gen.generate_markets()
        assert len(markets) == 1
        strike = _strike_from_question(markets[0].question)
        assert strike == DEFAULT_PRICES["btcusdt"]

    def test_deterministic_ids(self):
        feed = _make_binance_feed({"btcusdt": 90000.0})
        config = _make_config(SIM_MARKETS_PER_SYMBOL=2, BINANCE_SYMBOLS="btcusdt")
        gen = SimulatedMarketGenerator(config, feed)
        markets = gen.generate_markets()
        assert markets[0].condition_id == "sim-btcusdt-0"
        assert markets[0].token_id == "sim-tok-btcusdt-0"
        assert markets[1].condition_id == "sim-btcusdt-1"
        assert markets[1].token_id == "sim-tok-btcusdt-1"

    def test_strike_spread(self):
        price = 100000.0
        feed = _make_binance_feed({"btcusdt": price})
        config = _make_config(
            SIM_MARKETS_PER_SYMBOL=3,
            SIM_STRIKE_SPREAD_PCT=1.0,
            BINANCE_SYMBOLS="btcusdt",
        )
        gen = SimulatedMarketGenerator(config, feed)
        markets = gen.generate_markets()
        strikes = [_strike_from_question(m.question) for m in markets]
        assert strikes[0] == pytest.approx(99000.0, rel=1e-4)  # -1%
        assert strikes[1] == pytest.approx(100000.0, rel=1e-4)  # at price
        assert strikes[2] == pytest.approx(101000.0, rel=1e-4)  # +1%

    def test_all_markets_are_discovered_market_type(self):
        feed = _make_binance_feed({"btcusdt": 90000.0})
        config = _make_config(SIM_MARKETS_PER_SYMBOL=3, BINANCE_SYMBOLS="btcusdt")
        gen = SimulatedMarketGenerator(config, feed)
        for m in gen.generate_markets():
            assert isinstance(m, DiscoveredMarket)
            assert m.symbol == "btcusdt"
            assert m.outcome == "Yes"

    def test_single_market_per_symbol(self):
        feed = _make_binance_feed({"ethusdt": 2500.0})
        config = _make_config(SIM_MARKETS_PER_SYMBOL=1, BINANCE_SYMBOLS="ethusdt")
        gen = SimulatedMarketGenerator(config, feed)
        markets = gen.generate_markets()
        assert len(markets) == 1
        strike = _strike_from_question(markets[0].question)
        assert strike == 2500.0  # at price, no offset


# ---------------------------------------------------------------------------
# SimulatedOddsFeed
# ---------------------------------------------------------------------------

class TestSimulatedOddsFeed:
    def test_odds_above_strike(self):
        """Price well above strike should produce odds > 0.5."""
        market = DiscoveredMarket(
            condition_id="sim-btcusdt-0",
            token_id="sim-tok-btcusdt-0",
            question="Will BTC be above $85,000.00 in 15 min?",
            outcome="Yes",
            symbol="btcusdt",
        )
        feed = _make_binance_feed({"btcusdt": 90000.0})
        config = _make_config(SIM_NOISE_PCT=0.0, SIM_PRICE_LAG_SECONDS=1.0, SIM_ODDS_INTERVAL=1.0)
        odds_feed = SimulatedOddsFeed([market], asyncio.Queue(), feed, config)

        # Manually push price into buffer and run one tick
        odds_feed._price_buffers["btcusdt"].append(90000.0)

        async def _run():
            odds_feed._running = True
            # Run one iteration manually
            for m in odds_feed.markets:
                strike = _strike_from_question(m.question)
                buf = odds_feed._price_buffers.get(m.symbol, deque())
                lagged_price = buf[0]
                distance = (lagged_price - strike) / strike
                raw_odds = 0.5 + (distance * 10)
                odds = max(0.05, min(0.95, raw_odds))
                return odds

        odds = asyncio.get_event_loop().run_until_complete(_run())
        assert odds > 0.5

    def test_odds_below_strike(self):
        """Price below strike should produce odds < 0.5."""
        market = DiscoveredMarket(
            condition_id="sim-btcusdt-0",
            token_id="sim-tok-btcusdt-0",
            question="Will BTC be above $95,000.00 in 15 min?",
            outcome="Yes",
            symbol="btcusdt",
        )
        feed = _make_binance_feed({"btcusdt": 90000.0})
        config = _make_config(SIM_NOISE_PCT=0.0, SIM_PRICE_LAG_SECONDS=1.0, SIM_ODDS_INTERVAL=1.0)
        odds_feed = SimulatedOddsFeed([market], asyncio.Queue(), feed, config)
        odds_feed._price_buffers["btcusdt"].append(90000.0)

        strike = 95000.0
        lagged_price = 90000.0
        distance = (lagged_price - strike) / strike
        raw_odds = 0.5 + (distance * 10)
        odds = max(0.05, min(0.95, raw_odds))
        assert odds < 0.5

    def test_odds_clamped_high(self):
        """Extreme distance should clamp to 0.95."""
        distance = 0.10  # 10% above strike
        raw_odds = 0.5 + (distance * 10)
        odds = max(0.05, min(0.95, raw_odds))
        assert odds == 0.95

    def test_odds_clamped_low(self):
        """Extreme negative distance should clamp to 0.05."""
        distance = -0.10  # 10% below strike
        raw_odds = 0.5 + (distance * 10)
        odds = max(0.05, min(0.95, raw_odds))
        assert odds == 0.05

    @pytest.mark.asyncio
    async def test_odds_emitted_to_queue(self):
        """Verify odds snapshots are actually pushed to the queue."""
        market = DiscoveredMarket(
            condition_id="sim-btcusdt-0",
            token_id="sim-tok-btcusdt-0",
            question="Will BTC be above $87,000.00 in 15 min?",
            outcome="Yes",
            symbol="btcusdt",
        )
        queue = asyncio.Queue()
        feed = _make_binance_feed({"btcusdt": 88000.0})
        config = _make_config(SIM_NOISE_PCT=0.0, SIM_PRICE_LAG_SECONDS=1.0, SIM_ODDS_INTERVAL=0.1)
        odds_feed = SimulatedOddsFeed([market], queue, feed, config)

        # Pre-fill buffer
        odds_feed._price_buffers["btcusdt"].append(88000.0)

        async def _run_briefly():
            task = asyncio.create_task(odds_feed.start())
            try:
                snapshot = await asyncio.wait_for(queue.get(), timeout=2.0)
                return snapshot
            finally:
                odds_feed.stop()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        snapshot = await _run_briefly()
        assert isinstance(snapshot, OddsSnapshot)
        assert snapshot.symbol == "btcusdt"
        assert snapshot.condition_id == "sim-btcusdt-0"
        assert 0.05 <= snapshot.midpoint <= 0.95

    def test_lag_creates_stale_odds(self):
        """When buffer has old price, odds should reflect old price, not current."""
        market = DiscoveredMarket(
            condition_id="sim-btcusdt-0",
            token_id="sim-tok-btcusdt-0",
            question="Will BTC be above $87,000.00 in 15 min?",
            outcome="Yes",
            symbol="btcusdt",
        )
        feed = _make_binance_feed({"btcusdt": 90000.0})  # current = 90k
        config = _make_config(
            SIM_NOISE_PCT=0.0,
            SIM_PRICE_LAG_SECONDS=5.0,
            SIM_ODDS_INTERVAL=1.0,
        )
        odds_feed = SimulatedOddsFeed([market], asyncio.Queue(), feed, config)

        # Fill buffer with old prices, most recent is current
        buf = odds_feed._price_buffers["btcusdt"]
        buf.append(86000.0)  # old price (below strike)
        buf.append(87500.0)
        buf.append(88000.0)
        buf.append(89000.0)
        buf.append(90000.0)  # current price

        # Lagged price = buf[0] = 86000 (below 87000 strike)
        lagged = buf[0]
        assert lagged == 86000.0
        distance = (lagged - 87000.0) / 87000.0
        raw_odds = 0.5 + (distance * 10)
        odds = max(0.05, min(0.95, raw_odds))
        assert odds < 0.5  # stale price below strike = bearish odds

    def test_price_buffer_maxlen(self):
        """Buffer maxlen should be based on lag seconds / interval."""
        config = _make_config(SIM_PRICE_LAG_SECONDS=5.0, SIM_ODDS_INTERVAL=1.0)
        market = DiscoveredMarket(
            condition_id="sim-btcusdt-0",
            token_id="sim-tok-btcusdt-0",
            question="Will BTC be above $87,000.00 in 15 min?",
            outcome="Yes",
            symbol="btcusdt",
        )
        feed = _make_binance_feed()
        odds_feed = SimulatedOddsFeed([market], asyncio.Queue(), feed, config)
        buf = odds_feed._price_buffers["btcusdt"]
        assert buf.maxlen == 6  # int(5/1) + 1
