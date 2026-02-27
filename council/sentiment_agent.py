"""Sentiment agent: fast sentiment classification via nemotron."""
import logging
import re
import time

from council.prompts import SENTIMENT_PROMPT
from shared.ollama_client import OllamaClient
from shared.schemas import DivergenceSignal, Sentiment, SentimentResult

logger = logging.getLogger(__name__)

SENTIMENT_PATTERN = re.compile(r"SENTIMENT:\s*(BULLISH|BEARISH|NEUTRAL)", re.IGNORECASE)
REASONING_PATTERN = re.compile(r"REASONING:\s*(.+)", re.IGNORECASE)


class SentimentAgent:
    """Classifies market sentiment using a fast LLM."""

    def __init__(self, client: OllamaClient, model: str):
        self.client = client
        self.model = model

    async def analyze(self, signal: DivergenceSignal) -> SentimentResult:
        """Analyze divergence signal and return sentiment."""
        prompt = SENTIMENT_PROMPT.format(
            symbol=signal.symbol.upper(),
            price=signal.price,
            momentum_pct=signal.price_momentum_pct,
            direction=signal.direction,
            odds_midpoint=signal.odds_midpoint,
            implied_fair_odds=signal.implied_fair_odds,
            edge_pct=signal.edge_pct,
        )

        start = time.monotonic()
        try:
            result = await self.client.chat_async(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.3,
                max_tokens=2048,
            )
            latency = (time.monotonic() - start) * 1000

            response = result.get("response", "").strip()
            thinking = result.get("thinking", "").strip()
            merged = result["merged"]
            return self._parse(response, thinking, merged, latency)

        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            logger.error(f"Sentiment agent error: {e}")
            return SentimentResult(
                sentiment=Sentiment.NEUTRAL,
                reasoning=f"Error: {e}",
                model=self.model,
                latency_ms=latency,
            )

    def _parse(
        self, response: str, thinking: str, merged: str, latency_ms: float
    ) -> SentimentResult:
        """Parse LLM response into SentimentResult.

        Strategy: if response field has structured output, use it (clean).
        Otherwise fall back to last match in full text (thinking + response).
        """
        # Prefer response field (clean, structured output)
        sentiment_matches = SENTIMENT_PATTERN.findall(response) if response else []
        reasoning_matches = REASONING_PATTERN.findall(response) if response else []

        # Fall back to full merged text, take last match
        if not sentiment_matches:
            sentiment_matches = SENTIMENT_PATTERN.findall(merged)
        if not reasoning_matches:
            reasoning_matches = REASONING_PATTERN.findall(merged)

        sentiment = Sentiment.NEUTRAL  # fail-safe
        if sentiment_matches:
            raw = sentiment_matches[-1].upper()
            try:
                sentiment = Sentiment(raw)
            except ValueError:
                pass

        reasoning = ""
        if reasoning_matches:
            reasoning = reasoning_matches[-1].strip()[:500]
        else:
            clean = re.sub(r"<think>.*?</think>", "", merged, flags=re.DOTALL).strip()
            reasoning = clean[:200]

        return SentimentResult(
            sentiment=sentiment,
            reasoning=reasoning,
            model=self.model,
            latency_ms=latency_ms,
        )
