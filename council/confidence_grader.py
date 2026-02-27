"""Confidence grader: scores trade confidence 0-1 via qwen3."""
import logging
import re
import time

from council.prompts import CONFIDENCE_PROMPT
from shared.ollama_client import OllamaClient
from shared.schemas import DivergenceSignal, SentimentResult, ConfidenceGrade

logger = logging.getLogger(__name__)

CONFIDENCE_PATTERN = re.compile(r"CONFIDENCE:\s*([\d.]+)", re.IGNORECASE)
REASONING_PATTERN = re.compile(r"REASONING:\s*(.+)", re.IGNORECASE)


class ConfidenceGrader:
    """Grades confidence of a trade opportunity."""

    def __init__(self, client: OllamaClient, model: str):
        self.client = client
        self.model = model

    async def grade(
        self, signal: DivergenceSignal, sentiment: SentimentResult
    ) -> ConfidenceGrade:
        """Grade confidence given signal and sentiment."""
        prompt = CONFIDENCE_PROMPT.format(
            symbol=signal.symbol.upper(),
            price=signal.price,
            momentum_pct=signal.price_momentum_pct,
            odds_midpoint=signal.odds_midpoint,
            implied_fair_odds=signal.implied_fair_odds,
            edge_pct=signal.edge_pct,
            signal_score=signal.signal_score,
            sentiment=sentiment.sentiment.value,
            sentiment_reasoning=sentiment.reasoning,
        )

        start = time.monotonic()
        try:
            result = await self.client.chat_async(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.3,
                max_tokens=4096,
            )
            latency = (time.monotonic() - start) * 1000

            response = result.get("response", "").strip()
            thinking = result.get("thinking", "").strip()
            merged = result["merged"]
            logger.debug("Confidence grader raw", extra={
                "response_len": len(response),
                "thinking_len": len(thinking),
            })
            return self._parse(response, thinking, merged, latency)

        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            logger.error(f"Confidence grader error: {e}")
            return ConfidenceGrade(
                confidence=0.0,
                reasoning=f"Error: {e}",
                model=self.model,
                latency_ms=latency,
            )

    def _parse(
        self, response: str, thinking: str, merged: str, latency_ms: float
    ) -> ConfidenceGrade:
        """Parse LLM response into ConfidenceGrade.

        Strategy: if response field has structured output, use it (clean).
        Otherwise fall back to last match in full text (thinking + response).
        """
        # Prefer response field (clean, structured output)
        conf_matches = CONFIDENCE_PATTERN.findall(response) if response else []
        reasoning_matches = REASONING_PATTERN.findall(response) if response else []

        # Fall back to full merged text, take last match
        if not conf_matches:
            conf_matches = CONFIDENCE_PATTERN.findall(merged)
        if not reasoning_matches:
            reasoning_matches = REASONING_PATTERN.findall(merged)

        confidence = 0.0  # fail-safe = low confidence = SKIP
        if conf_matches:
            try:
                confidence = max(0.0, min(1.0, float(conf_matches[-1])))
            except ValueError:
                pass

        reasoning = ""
        if reasoning_matches:
            reasoning = reasoning_matches[-1].strip()[:500]
        else:
            clean = re.sub(r"<think>.*?</think>", "", merged, flags=re.DOTALL).strip()
            reasoning = clean[:200]

        return ConfidenceGrade(
            confidence=confidence,
            reasoning=reasoning,
            model=self.model,
            latency_ms=latency_ms,
        )
