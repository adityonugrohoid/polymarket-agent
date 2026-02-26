"""Pydantic models for all data flowing through the pipeline."""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class PriceTick(BaseModel):
    """Real-time price update from Binance WebSocket."""
    symbol: str
    price: float
    volume_24h: float = 0.0
    price_change_pct: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class OddsSnapshot(BaseModel):
    """Polymarket CLOB midpoint odds for a market."""
    condition_id: str
    token_id: str
    symbol: str
    question: str = ""
    outcome: str = ""
    midpoint: float
    spread: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DivergenceSignal(BaseModel):
    """Output of the divergence detector: price momentum vs stale odds."""
    symbol: str
    price: float
    price_momentum_pct: float
    odds_midpoint: float
    implied_fair_odds: float
    edge_pct: float
    signal_score: float
    direction: str  # "UP" or "DOWN"
    condition_id: str
    token_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Sentiment(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class SentimentResult(BaseModel):
    """Output of the sentiment agent."""
    sentiment: Sentiment
    reasoning: str = ""
    model: str = ""
    latency_ms: float = 0.0


class ConfidenceGrade(BaseModel):
    """Output of the confidence grader."""
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    model: str = ""
    latency_ms: float = 0.0


class TradeAction(str, Enum):
    TRADE = "TRADE"
    SKIP = "SKIP"


class TradeVerdict(BaseModel):
    """Output of the trade judge."""
    action: TradeAction
    size_usd: float = 0.0
    reasoning: str = ""
    model: str = ""
    latency_ms: float = 0.0


class CouncilDecision(BaseModel):
    """Aggregated output of the council of models."""
    signal: DivergenceSignal
    sentiment: SentimentResult
    confidence: ConfidenceGrade
    verdict: TradeVerdict
    total_latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderResult(BaseModel):
    """Result of an order placement (paper or live)."""
    order_id: str
    condition_id: str
    token_id: str
    symbol: str
    side: OrderSide
    size_usd: float
    price: float
    filled: bool = False
    is_paper: bool = True
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TradeRecord(BaseModel):
    """Persisted trade record in SQLite."""
    id: Optional[int] = None
    order_id: str
    symbol: str
    condition_id: str
    token_id: str
    side: str
    size_usd: float
    entry_price: float
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    is_paper: bool = True
    signal_score: float = 0.0
    sentiment: str = ""
    confidence: float = 0.0
    verdict: str = ""
    council_reasoning: str = ""
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
