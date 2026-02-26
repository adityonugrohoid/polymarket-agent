"""Tests for council.orchestrator."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from helpers import mcr

from council.orchestrator import CouncilOrchestrator
from shared.schemas import DivergenceSignal, TradeAction


def _make_signal():
    return DivergenceSignal(
        symbol="btcusdt", price=100000.0, price_momentum_pct=2.5,
        odds_midpoint=0.55, implied_fair_odds=0.625, edge_pct=7.5,
        signal_score=0.7, direction="UP", condition_id="c1", token_id="t1",
    )


@pytest.mark.asyncio
async def test_orchestrator_full_pipeline_trade():
    client = MagicMock()
    responses = [
        # Sentiment
        mcr(response="SENTIMENT: BULLISH\nREASONING: Strong upward momentum."),
        # Confidence
        mcr(response="CONFIDENCE: 0.85\nREASONING: Clear mispricing."),
        # Trade Judge
        mcr(response="DECISION: TRADE\nSIZE: $30\nREASONING: Good opportunity."),
    ]
    client.chat_async = AsyncMock(side_effect=responses)

    orchestrator = CouncilOrchestrator(
        client=client,
        model_sentiment="test-sent",
        model_grader="test-grade",
        model_judge="test-judge",
        min_confidence=0.6,
        max_position_size=50.0,
    )

    decision = await orchestrator.evaluate(_make_signal())
    assert decision.verdict.action == TradeAction.TRADE
    assert decision.verdict.size_usd == 30.0
    assert decision.sentiment.sentiment.value == "BULLISH"
    assert decision.confidence.confidence == pytest.approx(0.85, abs=0.01)
    assert client.chat_async.call_count == 3


@pytest.mark.asyncio
async def test_orchestrator_short_circuit_low_confidence():
    client = MagicMock()
    responses = [
        mcr(response="SENTIMENT: BULLISH\nREASONING: Some momentum."),
        mcr(response="CONFIDENCE: 0.3\nREASONING: Too noisy."),
        # Trade judge should NOT be called
    ]
    client.chat_async = AsyncMock(side_effect=responses)

    orchestrator = CouncilOrchestrator(
        client=client,
        model_sentiment="test-sent",
        model_grader="test-grade",
        model_judge="test-judge",
        min_confidence=0.6,
    )

    decision = await orchestrator.evaluate(_make_signal())
    assert decision.verdict.action == TradeAction.SKIP
    assert "short-circuit" in decision.verdict.model.lower()
    # Only sentiment + confidence called, judge skipped
    assert client.chat_async.call_count == 2
