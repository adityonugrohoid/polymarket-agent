"""Orchestrator: runs council agents sequentially with short-circuit logic."""
import logging
import time

from shared.ollama_client import OllamaClient
from shared.schemas import (
    DivergenceSignal,
    CouncilDecision,
    TradeAction,
    TradeVerdict,
    Sentiment,
    SentimentResult,
    ConfidenceGrade,
)
from council.sentiment_agent import SentimentAgent
from council.confidence_grader import ConfidenceGrader
from council.trade_judge import TradeJudge

logger = logging.getLogger(__name__)


class CouncilOrchestrator:
    """Runs the 3-agent council pipeline with short-circuit on low confidence."""

    def __init__(
        self,
        client: OllamaClient,
        model_sentiment: str,
        model_grader: str,
        model_judge: str,
        min_confidence: float = 0.6,
        max_position_size: float = 50.0,
    ):
        self.sentiment_agent = SentimentAgent(client, model_sentiment)
        self.confidence_grader = ConfidenceGrader(client, model_grader)
        self.trade_judge = TradeJudge(client, model_judge, max_position_size)
        self.min_confidence = min_confidence

    async def evaluate(
        self,
        signal: DivergenceSignal,
        available_capital: float = 1000.0,
    ) -> CouncilDecision:
        """Run the full council pipeline."""
        start = time.monotonic()

        # Step 1: Sentiment
        logger.info("Council: running sentiment agent", extra={"symbol": signal.symbol})
        sentiment = await self.sentiment_agent.analyze(signal)
        logger.info(
            "Council: sentiment result",
            extra={
                "sentiment": sentiment.sentiment.value,
                "latency_ms": round(sentiment.latency_ms),
            },
        )

        # Step 2: Confidence
        logger.info("Council: running confidence grader")
        confidence = await self.confidence_grader.grade(signal, sentiment)
        logger.info(
            "Council: confidence result",
            extra={
                "confidence": confidence.confidence,
                "latency_ms": round(confidence.latency_ms),
            },
        )

        # Short-circuit: if confidence is below threshold, SKIP
        if confidence.confidence < self.min_confidence:
            logger.info(
                "Council: short-circuit SKIP (low confidence)",
                extra={"confidence": confidence.confidence, "threshold": self.min_confidence},
            )
            total_latency = (time.monotonic() - start) * 1000
            return CouncilDecision(
                signal=signal,
                sentiment=sentiment,
                confidence=confidence,
                verdict=TradeVerdict(
                    action=TradeAction.SKIP,
                    size_usd=0.0,
                    reasoning=f"Short-circuit: confidence {confidence.confidence:.2f} < {self.min_confidence}",
                    model="short-circuit",
                    latency_ms=0.0,
                ),
                total_latency_ms=total_latency,
            )

        # Step 3: Trade Judge
        logger.info("Council: running trade judge")
        verdict = await self.trade_judge.judge(
            signal, sentiment, confidence, available_capital
        )
        logger.info(
            "Council: verdict",
            extra={
                "action": verdict.action.value,
                "size_usd": verdict.size_usd,
                "latency_ms": round(verdict.latency_ms),
            },
        )

        total_latency = (time.monotonic() - start) * 1000
        return CouncilDecision(
            signal=signal,
            sentiment=sentiment,
            confidence=confidence,
            verdict=verdict,
            total_latency_ms=total_latency,
        )
