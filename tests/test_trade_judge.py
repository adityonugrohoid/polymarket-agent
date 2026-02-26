"""Tests for council.trade_judge."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from helpers import mcr

from council.trade_judge import TradeJudge
from shared.schemas import (
    DivergenceSignal, SentimentResult, ConfidenceGrade,
    Sentiment, TradeAction,
)


def _make_signal():
    return DivergenceSignal(
        symbol="btcusdt", price=100000.0, price_momentum_pct=2.5,
        odds_midpoint=0.55, implied_fair_odds=0.625, edge_pct=7.5,
        signal_score=0.7, direction="UP", condition_id="c1", token_id="t1",
    )


def _make_sentiment():
    return SentimentResult(sentiment=Sentiment.BULLISH, reasoning="Strong momentum")


def _make_confidence(conf=0.85):
    return ConfidenceGrade(confidence=conf, reasoning="Clear edge")


@pytest.mark.asyncio
async def test_judge_trade():
    client = MagicMock()
    client.chat_async = AsyncMock(return_value=mcr(
        response="DECISION: TRADE\nSIZE: $25\nREASONING: Good edge, aligned signals."
    ))
    judge = TradeJudge(client, "test-model", max_position_size=50)
    result = await judge.judge(_make_signal(), _make_sentiment(), _make_confidence())
    assert result.action == TradeAction.TRADE
    assert result.size_usd == 25.0


@pytest.mark.asyncio
async def test_judge_skip():
    client = MagicMock()
    client.chat_async = AsyncMock(return_value=mcr(
        response="DECISION: SKIP\nSIZE: 0\nREASONING: Too risky."
    ))
    judge = TradeJudge(client, "test-model")
    result = await judge.judge(_make_signal(), _make_sentiment(), _make_confidence())
    assert result.action == TradeAction.SKIP
    assert result.size_usd == 0.0


@pytest.mark.asyncio
async def test_judge_size_clamped():
    client = MagicMock()
    client.chat_async = AsyncMock(return_value=mcr(
        response="DECISION: TRADE\nSIZE: $500\nREASONING: Go big."
    ))
    judge = TradeJudge(client, "test-model", max_position_size=50)
    result = await judge.judge(_make_signal(), _make_sentiment(), _make_confidence())
    assert result.action == TradeAction.TRADE
    assert result.size_usd == 50.0


@pytest.mark.asyncio
async def test_judge_parse_failure_defaults_skip():
    client = MagicMock()
    client.chat_async = AsyncMock(return_value=mcr(response="Garbage output"))
    judge = TradeJudge(client, "test-model")
    result = await judge.judge(_make_signal(), _make_sentiment(), _make_confidence())
    assert result.action == TradeAction.SKIP
