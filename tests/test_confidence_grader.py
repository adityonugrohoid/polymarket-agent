"""Tests for council.confidence_grader."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from helpers import mcr

from council.confidence_grader import ConfidenceGrader
from shared.schemas import DivergenceSignal, SentimentResult, Sentiment


def _make_signal():
    return DivergenceSignal(
        symbol="btcusdt", price=100000.0, price_momentum_pct=2.5,
        odds_midpoint=0.55, implied_fair_odds=0.625, edge_pct=7.5,
        signal_score=0.7, direction="UP", condition_id="c1", token_id="t1",
    )


def _make_sentiment():
    return SentimentResult(sentiment=Sentiment.BULLISH, reasoning="Strong momentum")


@pytest.mark.asyncio
async def test_confidence_high():
    client = MagicMock()
    client.chat_async = AsyncMock(return_value=mcr(
        response="CONFIDENCE: 0.85\nREASONING: Clear edge with strong momentum."
    ))
    grader = ConfidenceGrader(client, "test-model")
    result = await grader.grade(_make_signal(), _make_sentiment())
    assert result.confidence == pytest.approx(0.85, abs=0.01)


@pytest.mark.asyncio
async def test_confidence_low():
    client = MagicMock()
    client.chat_async = AsyncMock(return_value=mcr(
        response="CONFIDENCE: 0.25\nREASONING: Edge too small after fees."
    ))
    grader = ConfidenceGrader(client, "test-model")
    result = await grader.grade(_make_signal(), _make_sentiment())
    assert result.confidence == pytest.approx(0.25, abs=0.01)


@pytest.mark.asyncio
async def test_confidence_parse_failure_defaults_zero():
    client = MagicMock()
    client.chat_async = AsyncMock(return_value=mcr(response="No idea"))
    grader = ConfidenceGrader(client, "test-model")
    result = await grader.grade(_make_signal(), _make_sentiment())
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_confidence_clamped():
    client = MagicMock()
    client.chat_async = AsyncMock(return_value=mcr(
        response="CONFIDENCE: 1.5\nREASONING: Extremely confident"
    ))
    grader = ConfidenceGrader(client, "test-model")
    result = await grader.grade(_make_signal(), _make_sentiment())
    assert result.confidence == 1.0
