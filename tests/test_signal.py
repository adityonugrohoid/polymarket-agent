"""Tests for strategy.signal."""
from strategy.signal import score_edge, score_momentum, score_volume, composite_score


def test_score_edge_zero():
    assert score_edge(0.0) == 0.0


def test_score_edge_saturates():
    assert score_edge(10.0) == 1.0
    assert score_edge(20.0) == 1.0


def test_score_edge_linear():
    assert score_edge(5.0) == 0.5


def test_score_momentum_zero():
    assert score_momentum(0.0) == 0.0


def test_score_momentum_saturates():
    assert score_momentum(5.0) == 1.0
    assert score_momentum(-5.0) == 1.0


def test_score_volume_below_threshold():
    assert score_volume(100, 100) == 0.0  # ratio 1.0 < 1.5


def test_score_volume_above_threshold():
    # ratio = 3.0, normalized = (3.0 - 1.5) / 3.5 ≈ 0.4286
    result = score_volume(300, 100)
    assert 0.42 < result < 0.44


def test_composite_score_basic():
    score = composite_score(edge_pct=5.0, momentum_pct=2.5)
    # edge: 0.5 * 0.5 = 0.25, momentum: 0.5 * 0.3 = 0.15, volume: 0
    assert score == 0.4


def test_composite_score_max():
    score = composite_score(edge_pct=10.0, momentum_pct=5.0, volume_24h=500, avg_volume=100)
    # edge: 1.0*0.5=0.5, momentum: 1.0*0.3=0.3, volume: 1.0*0.2=0.2
    assert score == 1.0
