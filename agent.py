"""Main entry point — wires all layers together."""
import asyncio
import logging
import signal
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from shared.config import Config
from shared.logging import setup_logging
from shared.ollama_client import OllamaClient
from shared.schemas import CouncilDecision, TradeAction
from feeds.binance_ws import BinanceFeed
from feeds.gamma_discovery import GammaDiscovery
from feeds.polymarket_odds import PolymarketOddsFeed
from feeds.feed_aggregator import FeedAggregator, PairedData
from strategy.divergence_detector import DivergenceDetector
from council.orchestrator import CouncilOrchestrator
from execution.paper_trader import PaperTrader
from execution.position_tracker import PositionTracker
from storage.db import Database
from dashboard.main import app as dashboard_app, set_database

logger = setup_logging("polymarket-agent")


class TradingAgent:
    """Main trading agent orchestrating all components."""

    def __init__(self, config: Config):
        self.config = config
        self._shutdown = asyncio.Event()

        # Queues
        self.price_queue = asyncio.Queue(maxsize=1000)
        self.odds_queue = asyncio.Queue(maxsize=1000)
        self.paired_queue = asyncio.Queue(maxsize=500)
        self.signal_queue = asyncio.Queue(maxsize=100)

        # Components (initialized in start())
        self.db: Database | None = None
        self.binance_feed: BinanceFeed | None = None
        self.odds_feed: PolymarketOddsFeed | None = None
        self.aggregator: FeedAggregator | None = None
        self.detector: DivergenceDetector | None = None
        self.council: CouncilOrchestrator | None = None
        self.paper_trader: PaperTrader | None = None
        self.position_tracker: PositionTracker | None = None

    async def start(self):
        """Initialize and run all components."""
        logger.info(
            "Starting trading agent",
            extra={
                "mode": self.config.TRADING_MODE,
                "symbols": self.config.binance_symbols_list,
                "max_capital": self.config.MAX_CAPITAL,
            },
        )

        # Database
        self.db = Database(self.config.DB_PATH)
        await self.db.init()

        # Position tracker
        self.position_tracker = PositionTracker(
            self.db,
            max_capital=self.config.MAX_CAPITAL,
            max_position_size=self.config.MAX_POSITION_SIZE,
            max_open_positions=self.config.MAX_OPEN_POSITIONS,
        )

        # Discover markets
        discovery = GammaDiscovery()
        markets = await discovery.discover()
        if not markets:
            logger.warning("No crypto markets found on Polymarket, running in price-only mode")

        # Feeds
        self.binance_feed = BinanceFeed(
            self.config.binance_symbols_list, self.price_queue
        )
        self.odds_feed = PolymarketOddsFeed(
            markets, self.odds_queue, poll_interval=5.0
        )
        self.aggregator = FeedAggregator(
            self.price_queue, self.odds_queue, self.paired_queue, markets
        )

        # Strategy
        self.detector = DivergenceDetector(
            self.paired_queue,
            self.signal_queue,
            self.binance_feed,
            min_edge_pct=self.config.MIN_EDGE_PCT,
            min_signal_score=self.config.MIN_SIGNAL_SCORE,
        )

        # Council
        ollama = OllamaClient(
            host=self.config.OLLAMA_HOST,
            model=self.config.LLM_MODEL_SENTIMENT,
        )
        self.council = CouncilOrchestrator(
            client=ollama,
            model_sentiment=self.config.LLM_MODEL_SENTIMENT,
            model_grader=self.config.LLM_MODEL_GRADER,
            model_judge=self.config.LLM_MODEL_JUDGE,
            min_confidence=self.config.MIN_CONFIDENCE,
            max_position_size=self.config.MAX_POSITION_SIZE,
        )

        # Execution
        self.paper_trader = PaperTrader(self.db, self.position_tracker)

        # Dashboard
        set_database(self.db)

        # Run all tasks
        tasks = [
            asyncio.create_task(self.binance_feed.start(), name="binance"),
            asyncio.create_task(self.odds_feed.start(), name="odds"),
            asyncio.create_task(self.aggregator.start(), name="aggregator"),
            asyncio.create_task(self.detector.start(), name="detector"),
            asyncio.create_task(self._council_loop(), name="council"),
            asyncio.create_task(self._status_loop(), name="status"),
            asyncio.create_task(self._run_dashboard(), name="dashboard"),
        ]

        logger.info("All components started")

        # Wait for shutdown signal
        await self._shutdown.wait()

        # Cleanup
        logger.info("Shutting down...")
        self.binance_feed.stop()
        self.odds_feed.stop()
        self.aggregator.stop()
        self.detector.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.db.close()
        logger.info("Shutdown complete")

    async def _council_loop(self):
        """Consume divergence signals and run through council."""
        cooldown_until: dict[str, float] = {}

        while not self._shutdown.is_set():
            try:
                signal = await asyncio.wait_for(
                    self.signal_queue.get(), timeout=5.0
                )
            except asyncio.TimeoutError:
                continue

            # Cooldown check
            now = time.monotonic()
            last = cooldown_until.get(signal.symbol, 0)
            if now < last:
                logger.debug(
                    "Signal in cooldown",
                    extra={"symbol": signal.symbol},
                )
                continue

            # Log signal
            await self.db.log_signal({
                "symbol": signal.symbol,
                "price": signal.price,
                "momentum_pct": signal.price_momentum_pct,
                "odds_midpoint": signal.odds_midpoint,
                "implied_fair_odds": signal.implied_fair_odds,
                "edge_pct": signal.edge_pct,
                "signal_score": signal.signal_score,
                "direction": signal.direction,
            })

            # Run council
            available = await self.position_tracker.get_available_capital()
            decision = await self.council.evaluate(signal, available)

            # Execute
            if decision.verdict.action == TradeAction.TRADE:
                if self.config.is_live:
                    logger.info("Live trading not yet implemented, using paper trader")
                order = await self.paper_trader.execute(decision)
                if order:
                    cooldown_until[signal.symbol] = now + self.config.COOLDOWN_SECONDS

    async def _status_loop(self):
        """Periodically log status."""
        while not self._shutdown.is_set():
            await asyncio.sleep(60)
            try:
                summary = await self.db.get_pnl_summary()
                open_count = await self.position_tracker.get_open_count()
                available = await self.position_tracker.get_available_capital()
                logger.info(
                    "Status update",
                    extra={
                        "total_trades": summary["total_trades"],
                        "win_rate": f"{summary['win_rate']:.1f}%",
                        "total_pnl": f"${summary['total_pnl']:.2f}",
                        "open_positions": open_count,
                        "available_capital": f"${available:.2f}",
                    },
                )
            except Exception as e:
                logger.error(f"Status loop error: {e}")

    async def _run_dashboard(self):
        """Run the FastAPI dashboard."""
        import uvicorn
        config = uvicorn.Config(
            dashboard_app,
            host="0.0.0.0",
            port=self.config.DASHBOARD_PORT,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        logger.info(
            "Dashboard starting",
            extra={"port": self.config.DASHBOARD_PORT},
        )
        await server.serve()

    def shutdown(self):
        self._shutdown.set()


def main():
    config = Config.from_env()

    agent = TradingAgent(config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def handle_signal(sig, frame):
        logger.info(f"Received signal {sig}")
        agent.shutdown()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        loop.run_until_complete(agent.start())
    except KeyboardInterrupt:
        agent.shutdown()
        loop.run_until_complete(asyncio.sleep(1))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
