"""Tests for strategy.divergence_detector."""
import asyncio
import pytest
from collections import deque
from unittest.mock import MagicMock

from feeds.feed_aggregator import PairedData
from shared.schemas import PriceTick, OddsSnapshot
from strategy.divergence_detector import DivergenceDetector, compute_implied_odds


def test_compute_implied_odds_bullish():
    # 2% momentum should push odds up by ~6%
    implied = compute_implied_odds(0.50, 2.0)
    assert implied == pytest.approx(0.56, abs=0.01)


def test_compute_implied_odds_bearish():
    implied = compute_implied_odds(0.50, -2.0)
    assert implied == pytest.approx(0.44, abs=0.01)


def test_compute_implied_odds_clamped():
    assert compute_implied_odds(0.99, 5.0) == 0.99
    assert compute_implied_odds(0.01, -5.0) == 0.01


def _make_detector(momentum: float = 3.0) -> tuple:
    """Create a detector with mocked binance feed."""
    paired_q = asyncio.Queue()
    signal_q = asyncio.Queue()

    binance_feed = MagicMock()
    binance_feed.get_momentum.return_value = momentum

    detector = DivergenceDetector(
        paired_queue=paired_q,
        signal_queue=signal_q,
        binance_feed=binance_feed,
        min_edge_pct=2.0,
        min_signal_score=0.3,  # Lower for testing
    )
    return detector, paired_q, signal_q


def test_evaluate_strong_signal():
    detector, _, _ = _make_detector(momentum=3.0)

    tick = PriceTick(symbol="btcusdt", price=100000.0, volume_24h=5000)
    odds = OddsSnapshot(
        condition_id="cond1", token_id="tok1",
        symbol="btcusdt", midpoint=0.50,
    )
    paired = PairedData(tick=tick, odds=odds)

    signal = detector._evaluate(paired)
    assert signal is not None
    assert signal.direction == "UP"
    assert signal.edge_pct > 2.0
    assert signal.signal_score > 0.0


def test_evaluate_weak_momentum_skipped():
    detector, _, _ = _make_detector(momentum=0.1)

    tick = PriceTick(symbol="btcusdt", price=100000.0)
    odds = OddsSnapshot(
        condition_id="cond1", token_id="tok1",
        symbol="btcusdt", midpoint=0.50,
    )
    paired = PairedData(tick=tick, odds=odds)

    signal = detector._evaluate(paired)
    assert signal is None
