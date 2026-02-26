"""Signal scoring: composite 0-1 score from edge, momentum, volume."""
from strategy.thresholds import (
    WEIGHT_EDGE,
    WEIGHT_MOMENTUM,
    WEIGHT_VOLUME,
    VOLUME_SPIKE_THRESHOLD,
)


def score_edge(edge_pct: float) -> float:
    """Score the edge component (0-1). Saturates at 10%."""
    return min(abs(edge_pct) / 10.0, 1.0)


def score_momentum(momentum_pct: float) -> float:
    """Score momentum component (0-1). Saturates at 5%."""
    return min(abs(momentum_pct) / 5.0, 1.0)


def score_volume(volume_24h: float, avg_volume: float) -> float:
    """Score volume spike relative to average (0-1)."""
    if avg_volume <= 0:
        return 0.0
    ratio = volume_24h / avg_volume
    if ratio < VOLUME_SPIKE_THRESHOLD:
        return 0.0
    # Normalize: 1.5x = 0, 5x = 1.0
    return min((ratio - VOLUME_SPIKE_THRESHOLD) / 3.5, 1.0)


def composite_score(
    edge_pct: float,
    momentum_pct: float,
    volume_24h: float = 0.0,
    avg_volume: float = 0.0,
) -> float:
    """Calculate weighted composite signal score (0-1)."""
    e = score_edge(edge_pct) * WEIGHT_EDGE
    m = score_momentum(momentum_pct) * WEIGHT_MOMENTUM
    v = score_volume(volume_24h, avg_volume) * WEIGHT_VOLUME
    return round(e + m + v, 4)
