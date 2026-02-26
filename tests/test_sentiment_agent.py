"""Tests for council.sentiment_agent."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from helpers import mcr

from council.sentiment_agent import SentimentAgent
from shared.schemas import DivergenceSignal, Sentiment


def _make_signal(**kwargs):
    defaults = dict(
        symbol="btcusdt", price=100000.0, price_momentum_pct=2.5,
        odds_midpoint=0.55, implied_fair_odds=0.625, edge_pct=7.5,
        signal_score=0.7, direction="UP", condition_id="c1", token_id="t1",
    )
    defaults.update(kwargs)
    return DivergenceSignal(**defaults)


@pytest.mark.asyncio
async def test_sentiment_bullish():
    client = MagicMock()
    client.chat_async = AsyncMock(return_value=mcr(
        response="SENTIMENT: BULLISH\nREASONING: Strong upward momentum indicates buying pressure."
    ))
    agent = SentimentAgent(client, "test-model")
    result = await agent.analyze(_make_signal())
    assert result.sentiment == Sentiment.BULLISH
    assert "momentum" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_sentiment_bearish():
    client = MagicMock()
    client.chat_async = AsyncMock(return_value=mcr(
        response="SENTIMENT: BEARISH\nREASONING: Price dropping fast."
    ))
    agent = SentimentAgent(client, "test-model")
    result = await agent.analyze(_make_signal(direction="DOWN", price_momentum_pct=-3.0))
    assert result.sentiment == Sentiment.BEARISH


@pytest.mark.asyncio
async def test_sentiment_parse_failure_defaults_neutral():
    client = MagicMock()
    client.chat_async = AsyncMock(return_value=mcr(response="I'm not sure what to say"))
    agent = SentimentAgent(client, "test-model")
    result = await agent.analyze(_make_signal())
    assert result.sentiment == Sentiment.NEUTRAL


@pytest.mark.asyncio
async def test_sentiment_error_defaults_neutral():
    client = MagicMock()
    client.chat_async = AsyncMock(side_effect=Exception("API down"))
    agent = SentimentAgent(client, "test-model")
    result = await agent.analyze(_make_signal())
    assert result.sentiment == Sentiment.NEUTRAL
