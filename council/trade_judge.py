"""Trade judge: final TRADE/SKIP decision via gpt-oss."""
import logging
import re
import time

from council.prompts import TRADE_JUDGE_PROMPT
from shared.ollama_client import OllamaClient
from shared.schemas import (
    DivergenceSignal,
    SentimentResult,
    ConfidenceGrade,
    TradeAction,
    TradeVerdict,
)

logger = logging.getLogger(__name__)

DECISION_PATTERN = re.compile(r"DECISION:\s*(TRADE|SKIP)", re.IGNORECASE)
SIZE_PATTERN = re.compile(r"SIZE:\s*\$?([\d.]+)", re.IGNORECASE)
REASONING_PATTERN = re.compile(r"REASONING:\s*(.+)", re.IGNORECASE | re.DOTALL)


class TradeJudge:
    """Makes the final trade/skip decision."""

    def __init__(
        self,
        client: OllamaClient,
        model: str,
        max_position_size: float = 50.0,
    ):
        self.client = client
        self.model = model
        self.max_position_size = max_position_size

    async def judge(
        self,
        signal: DivergenceSignal,
        sentiment: SentimentResult,
        confidence: ConfidenceGrade,
        available_capital: float = 1000.0,
    ) -> TradeVerdict:
        """Make final trade decision."""
        prompt = TRADE_JUDGE_PROMPT.format(
            symbol=signal.symbol.upper(),
            price=signal.price,
            momentum_pct=signal.price_momentum_pct,
            odds_midpoint=signal.odds_midpoint,
            implied_fair_odds=signal.implied_fair_odds,
            edge_pct=signal.edge_pct,
            signal_score=signal.signal_score,
            sentiment=sentiment.sentiment.value,
            sentiment_reasoning=sentiment.reasoning,
            confidence=confidence.confidence,
            confidence_reasoning=confidence.reasoning,
            max_position_size=self.max_position_size,
            available_capital=available_capital,
        )

        start = time.monotonic()
        try:
            result = await self.client.chat_async(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.2,
                max_tokens=2048,
            )
            latency = (time.monotonic() - start) * 1000

            response = result.get("response", "").strip()
            thinking = result.get("thinking", "").strip()
            merged = result["merged"]
            return self._parse(response, thinking, merged, latency)

        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            logger.error(f"Trade judge error: {e}")
            return TradeVerdict(
                action=TradeAction.SKIP,
                size_usd=0.0,
                reasoning=f"Error: {e}",
                model=self.model,
                latency_ms=latency,
            )

    def _parse(
        self, response: str, thinking: str, merged: str, latency_ms: float
    ) -> TradeVerdict:
        """Parse LLM response into TradeVerdict.

        Strategy: if response field has structured output, use it (clean).
        Otherwise fall back to last match in full text (thinking + response).
        """
        # Prefer response field (clean, structured output)
        decision_matches = DECISION_PATTERN.findall(response) if response else []
        size_matches = SIZE_PATTERN.findall(response) if response else []
        reasoning_matches = REASONING_PATTERN.findall(response) if response else []

        # Fall back to full merged text, take last match
        if not decision_matches:
            decision_matches = DECISION_PATTERN.findall(merged)
        if not size_matches:
            size_matches = SIZE_PATTERN.findall(merged)
        if not reasoning_matches:
            reasoning_matches = REASONING_PATTERN.findall(merged)

        action = TradeAction.SKIP  # fail-safe
        size_usd = 0.0

        if decision_matches:
            raw = decision_matches[-1].upper()
            try:
                action = TradeAction(raw)
            except ValueError:
                action = TradeAction.SKIP

        if action == TradeAction.TRADE and size_matches:
            try:
                size_usd = float(size_matches[-1])
                # Clamp to position limits
                size_usd = max(5.0, min(size_usd, self.max_position_size))
            except ValueError:
                size_usd = 0.0
                action = TradeAction.SKIP

        if action == TradeAction.TRADE and size_usd <= 0:
            action = TradeAction.SKIP

        reasoning = ""
        if reasoning_matches:
            reasoning = reasoning_matches[-1].strip()[:500]
        else:
            clean = re.sub(r"<think>.*?</think>", "", merged, flags=re.DOTALL).strip()
            reasoning = clean[:200]

        return TradeVerdict(
            action=action,
            size_usd=size_usd,
            reasoning=reasoning,
            model=self.model,
            latency_ms=latency_ms,
        )
