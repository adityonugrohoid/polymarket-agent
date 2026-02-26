"""Tests for feeds.feed_aggregator."""
import asyncio
import pytest
from datetime import datetime

from feeds.feed_aggregator import FeedAggregator, PairedData
from feeds.gamma_discovery import DiscoveredMarket
from shared.schemas import PriceTick, OddsSnapshot


@pytest.mark.asyncio
async def test_aggregator_pairs_price_with_odds():
    """Aggregator should emit PairedData when price and odds match."""
    price_q = asyncio.Queue()
    odds_q = asyncio.Queue()
    signal_q = asyncio.Queue()

    market = DiscoveredMarket(
        condition_id="cond1",
        token_id="tok1",
        question="Will BTC hit 100k?",
        outcome="Yes",
        symbol="btcusdt",
    )

    agg = FeedAggregator(price_q, odds_q, signal_q, [market])

    # Seed odds first
    odds = OddsSnapshot(
        condition_id="cond1",
        token_id="tok1",
        symbol="btcusdt",
        midpoint=0.65,
    )
    await odds_q.put(odds)

    # Then price tick
    tick = PriceTick(symbol="btcusdt", price=99500.0)
    await price_q.put(tick)

    # Run aggregator briefly
    task = asyncio.create_task(agg.start())
    await asyncio.sleep(0.3)
    agg.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert not signal_q.empty()
    paired = await signal_q.get()
    assert isinstance(paired, PairedData)
    assert paired.tick.symbol == "btcusdt"
    assert paired.odds.midpoint == 0.65


@pytest.mark.asyncio
async def test_aggregator_no_odds_no_emission():
    """No paired signal if odds haven't arrived yet."""
    price_q = asyncio.Queue()
    odds_q = asyncio.Queue()
    signal_q = asyncio.Queue()

    market = DiscoveredMarket(
        condition_id="cond1",
        token_id="tok1",
        question="Will ETH hit 5k?",
        outcome="Yes",
        symbol="ethusdt",
    )

    agg = FeedAggregator(price_q, odds_q, signal_q, [market])

    # Only price, no odds
    tick = PriceTick(symbol="ethusdt", price=3500.0)
    await price_q.put(tick)

    task = asyncio.create_task(agg.start())
    await asyncio.sleep(0.3)
    agg.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert signal_q.empty()
