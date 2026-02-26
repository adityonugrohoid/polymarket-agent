"""Configurable constants for the strategy layer."""

# Minimum edge (%) between implied fair odds and market odds to trigger signal
MIN_EDGE_PCT = 2.0

# Minimum composite signal score (0-1) to pass to council
MIN_SIGNAL_SCORE = 0.6

# Minimum price momentum (%) to consider meaningful
MIN_MOMENTUM_PCT = 0.3

# Weight factors for composite signal scoring
WEIGHT_EDGE = 0.5
WEIGHT_MOMENTUM = 0.3
WEIGHT_VOLUME = 0.2

# Volume percentile threshold (relative to 24h average) for volume factor
VOLUME_SPIKE_THRESHOLD = 1.5
