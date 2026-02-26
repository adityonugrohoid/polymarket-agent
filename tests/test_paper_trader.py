"""Tests for execution.paper_trader."""
import asyncio
import os
import pytest
import pytest_asyncio

from execution.paper_trader import PaperTrader
from execution.position_tracker import PositionTracker
from shared.schemas import (
    CouncilDecision, DivergenceSignal, SentimentResult,
    ConfidenceGrade, TradeVerdict, TradeAction, Sentiment, OrderSide,
)
from storage.db import Database


def _make_decision(action=TradeAction.TRADE, size=25.0):
    signal = DivergenceSignal(
        symbol="btcusdt", price=100000.0, price_momentum_pct=2.5,
        odds_midpoint=0.55, implied_fair_odds=0.625, edge_pct=7.5,
        signal_score=0.7, direction="UP", condition_id="c1", token_id="t1",
    )
    return CouncilDecision(
        signal=signal,
        sentiment=SentimentResult(sentiment=Sentiment.BULLISH, reasoning="Strong"),
        confidence=ConfidenceGrade(confidence=0.85, reasoning="Clear edge"),
        verdict=TradeVerdict(action=action, size_usd=size, reasoning="Good trade"),
    )


@pytest_asyncio.fixture
async def paper_env(tmp_path):
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)
    await db.init()
    tracker = PositionTracker(db, max_capital=1000, max_position_size=50, max_open_positions=3)
    trader = PaperTrader(db, tracker)
    yield trader, db
    await db.close()


@pytest.mark.asyncio
async def test_paper_trade_executes(paper_env):
    trader, db = paper_env
    decision = _make_decision()
    order = await trader.execute(decision)
    assert order is not None
    assert order.filled is True
    assert order.is_paper is True
    assert order.side == OrderSide.BUY
    assert order.size_usd == 25.0

    # Verify persisted in DB
    trades = await db.get_recent_trades()
    assert len(trades) == 1
    assert trades[0]["symbol"] == "btcusdt"


@pytest.mark.asyncio
async def test_paper_trade_skip_decision(paper_env):
    trader, db = paper_env
    decision = _make_decision(action=TradeAction.SKIP)
    order = await trader.execute(decision)
    assert order is None


@pytest.mark.asyncio
async def test_paper_trade_blocked_by_position_limit(paper_env):
    trader, db = paper_env
    # Fill up positions
    for _ in range(3):
        await trader.execute(_make_decision(size=10.0))

    # 4th should be blocked
    order = await trader.execute(_make_decision(size=10.0))
    assert order is None


@pytest.mark.asyncio
async def test_pnl_summary(paper_env):
    trader, db = paper_env
    await trader.execute(_make_decision(size=20.0))
    summary = await db.get_pnl_summary()
    assert summary["total_trades"] == 1
    assert summary["open"] == 1
