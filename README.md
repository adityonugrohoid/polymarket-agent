# Polymarket AI Trading Agent

An autonomous crypto trading agent that detects price divergences between Binance spot markets and Polymarket prediction market odds, then runs a council of 3 LLMs to make intelligent trade decisions.

## Architecture

```
Binance WebSocket ──► price_queue ──► FeedAggregator ──► DivergenceDetector ──► signal_queue
                                          ▲                                         │
Polymarket CLOB ────► odds_queue ─────────┘                                         ▼
                                                                            CouncilOrchestrator
                                                                           ┌────────┴────────┐
                                                                           │  1. Sentiment    │ nemotron-3-nano:30b
                                                                           │  2. Confidence   │ qwen3-next:80b
                                                                           │  3. Trade Judge  │ gpt-oss:120b
                                                                           └────────┬────────┘
                                                                                    │
                                                                                    ▼
                                                                              PaperTrader
                                                                                    │
                                                                                    ▼
                                                                           SQLite + Dashboard
```

## How It Works

### 1. Data Feeds
- **Binance WebSocket** streams real-time prices for BTC, ETH, SOL with rolling 20-tick momentum calculation
- **Polymarket CLOB** polls prediction market odds every 5 seconds via midpoint API
- **Feed Aggregator** pairs each price tick with the latest odds for the same symbol

### 2. Divergence Detection
The strategy layer computes:
- **Implied fair odds** = market odds + (momentum * 0.03) — a 1% price move adjusts odds by 3%
- **Edge** = implied fair odds - market odds — the mispricing percentage
- **Composite score** = weighted combination of edge (50%), momentum (30%), volume (20%)

Signals fire when edge > `MIN_EDGE_PCT` and score > `MIN_SIGNAL_SCORE`.

### 3. Council of Models
Three LLMs evaluate each signal sequentially:

| Agent | Model | Role | Output |
|-------|-------|------|--------|
| Sentiment | nemotron-3-nano:30b | Fast sentiment classification | BULLISH / BEARISH / NEUTRAL + reasoning |
| Confidence | qwen3-next:80b | Quantitative signal quality grading | Float 0.0-1.0 + reasoning |
| Trade Judge | gpt-oss:120b | Final trade/skip decision with sizing | TRADE/SKIP + dollar amount + reasoning |

**Short-circuit**: If confidence < `MIN_CONFIDENCE`, the pipeline skips the trade judge entirely.

**Thinking-mode support**: All parsers handle models that use extended thinking (`think=True`). When the model produces a response field, it's parsed directly. When the model puts everything in the thinking field (common with reasoning models), the parser searches the full text and takes the last match to avoid echoed prompt content.

### 4. Execution
- **Paper Trading** (current): Simulates fills at market midpoint, logs to SQLite with full council reasoning
- **Live Trading** (scaffolded): `OrderManager` + `PolymarketClient` for authenticated CLOB order placement on Polygon

### 5. Risk Management
Enforced at the execution layer before every trade:
- Max open positions: `MAX_OPEN_POSITIONS` (default 3)
- Max position size: `MAX_POSITION_SIZE` (default $50)
- Max portfolio exposure: `MAX_CAPITAL` (default $1000)
- Per-symbol cooldown: `COOLDOWN_SECONDS` after each trade

## Simulation Mode

Since Polymarket currently has no short-term crypto price markets (only long-dated events like "BTC hits $150k by June 2026"), the agent includes a full simulation layer for testing and development.

`SIMULATION_MODE=true` activates:

- **SimulatedMarketGenerator** — Creates synthetic 15-minute prediction markets at 3 strike levels per symbol (current price -1%, 0%, +1%). Example: "Will BTC be above $87,000.00 in 15 min?"
- **SimulatedOddsFeed** — Computes odds from a deliberately lagged price buffer. Real price moves but odds use a 5-second-old price, naturally creating divergence opportunities
- **SimulatedPriceFeed** — Gaussian random walk (mean +0.08%, stddev 1.2% per tick) injected into Binance feed's price history so momentum calculations work normally

The simulation is fully self-contained — no external API calls needed (except Ollama for LLM inference). Removable by deleting `feeds/simulation.py` and the config branch in `agent.py`.

### Odds Calculation
```
distance = (lagged_price - strike) / strike
raw_odds = 0.5 + (distance * 10)        # 1% above strike = 0.6 odds
odds = clamp(raw_odds + noise, 0.05, 0.95)
```

## Project Structure

```
polymarket-agent/
├── agent.py                    # Main entry point, wires all components
├── feeds/
│   ├── binance_ws.py           # Binance WebSocket price streaming
│   ├── polymarket_odds.py      # CLOB midpoint polling
│   ├── gamma_discovery.py      # Polymarket market discovery via Gamma API
│   ├── feed_aggregator.py      # Pairs price ticks with odds by symbol
│   └── simulation.py           # Synthetic markets, odds, and prices
├── strategy/
│   ├── divergence_detector.py  # Core divergence detection algorithm
│   ├── signal.py               # Composite signal scoring (edge, momentum, volume)
│   └── thresholds.py           # Default strategy constants
├── council/
│   ├── orchestrator.py         # 3-agent pipeline with short-circuit logic
│   ├── sentiment_agent.py      # Sentiment classification (Agent 1)
│   ├── confidence_grader.py    # Confidence scoring 0-1 (Agent 2)
│   ├── trade_judge.py          # Final TRADE/SKIP decision (Agent 3)
│   └── prompts.py              # Prompt templates for all 3 agents
├── execution/
│   ├── paper_trader.py         # Simulated trade execution
│   ├── order_manager.py        # Live Polymarket CLOB order placement
│   ├── polymarket_client.py    # Authenticated CLOB client wrapper
│   └── position_tracker.py     # Risk limits enforcement
├── storage/
│   ├── db.py                   # Async SQLite wrapper (aiosqlite)
│   └── models.py               # Table schemas (trades, signals)
├── shared/
│   ├── config.py               # Environment variable management (Pydantic)
│   ├── schemas.py              # Data models for the entire pipeline
│   ├── ollama_client.py        # LLM client with thinking-mode support
│   └── logging.py              # Structured JSON logging
├── dashboard/
│   ├── main.py                 # FastAPI web dashboard
│   └── templates/index.html    # Dashboard HTML template
├── tests/                      # 55 tests, 908 lines
│   ├── test_simulation.py      # Simulation layer tests
│   ├── test_divergence_detector.py
│   ├── test_feed_aggregator.py
│   ├── test_sentiment_agent.py
│   ├── test_confidence_grader.py
│   ├── test_trade_judge.py
│   ├── test_orchestrator.py
│   ├── test_paper_trader.py
│   ├── test_signal.py
│   └── test_config.py
├── .env.example                # Configuration template
└── requirements.txt            # Python dependencies
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Trading
TRADING_MODE=paper              # paper or live
BINANCE_SYMBOLS=btcusdt,ethusdt,solusdt

# LLM (Ollama Cloud or local)
OLLAMA_HOST=https://ollama.com  # or http://localhost:11434
OLLAMA_API_KEY=your_key_here
LLM_MODEL_SENTIMENT=nemotron-3-nano:30b
LLM_MODEL_GRADER=qwen3-next:80b
LLM_MODEL_JUDGE=gpt-oss:120b

# Strategy thresholds
MIN_EDGE_PCT=0.5                # Minimum mispricing % to trigger signal
MIN_SIGNAL_SCORE=0.15           # Minimum composite score (0-1)
MIN_CONFIDENCE=0.3              # LLM confidence threshold for trade judge

# Risk management
MAX_CAPITAL=1000                # Total portfolio cap ($)
MAX_POSITION_SIZE=50            # Per-trade limit ($)
MAX_OPEN_POSITIONS=3            # Max concurrent positions
COOLDOWN_SECONDS=30             # Per-symbol cooldown after trade

# Simulation (set SIMULATION_MODE=true to use synthetic feeds)
SIMULATION_MODE=true
SIM_MARKETS_PER_SYMBOL=3
SIM_STRIKE_SPREAD_PCT=1.0
SIM_PRICE_LAG_SECONDS=5.0
SIM_NOISE_PCT=2.0
SIM_ODDS_INTERVAL=1.0

# Infrastructure
DASHBOARD_PORT=8081
DB_PATH=data/trades.db
```

## Running

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your Ollama API key

# Run
python agent.py

# Dashboard available at http://localhost:8081
```

## Example Council Output

A complete council evaluation cycle from a live simulation run:

```
Signal: BTCUSDT | Price: $89,086.17 | Momentum: +2.22% | Edge: +6.67% | Score: 0.4671 | Direction: UP

Agent 1 — Sentiment (nemotron-3-nano:30b, 1554ms):
  BULLISH — "The upward momentum and positive edge indicate a bullish outlook."

Agent 2 — Confidence (qwen3-next:80b, 15063ms):
  0.47 — "Score below 0.5 indicates low confidence due to momentum sustainability
          concerns despite positive edge."

Agent 3 — Trade Judge (gpt-oss:120b, 1801ms):
  SKIP, $0
```

When the judge decides to trade:

```
Signal: BTCUSDT | Edge: +6.58% | Score: 0.4606

Agent 1 — Sentiment: BULLISH
Agent 2 — Confidence: 0.46
Agent 3 — Trade Judge: TRADE, $10
  "Positive edge (+6.58%) suggests a favorable expected value despite low confidence,
   so a modest $10 position limits risk while capturing upside."

Paper trade executed: BUY btcusdt $10.00 @ 0.5096
```

## Database Schema

```sql
-- Full trade lifecycle with council reasoning
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE, symbol TEXT, condition_id TEXT, token_id TEXT,
    side TEXT, size_usd REAL, entry_price REAL, exit_price REAL, pnl REAL,
    is_paper INTEGER, signal_score REAL, sentiment TEXT, confidence REAL,
    verdict TEXT, council_reasoning TEXT, opened_at TEXT, closed_at TEXT
);

-- All divergence signals for backtesting
CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT, price REAL, momentum_pct REAL, odds_midpoint REAL,
    implied_fair_odds REAL, edge_pct REAL, signal_score REAL,
    direction TEXT, council_action TEXT, timestamp TEXT
);
```

## Tests

```bash
# Run all 55 tests
python -m pytest tests/ -q

# Run specific module
python -m pytest tests/test_simulation.py -v
```

## Current Status

- **Paper trading**: Fully functional end-to-end pipeline
- **Simulation mode**: Working — synthetic markets fire divergence signals within seconds, council evaluates, paper trades execute
- **LLM integration**: 3 models via Ollama Cloud with thinking-mode support
- **Live trading**: Scaffolded (`OrderManager` + `PolymarketClient`) but not wired in `agent.py`
- **Binance connectivity**: Requires direct access or VPN (blocked by some ISPs)
- **Dashboard**: FastAPI at port 8081 with trade history and P&L summary

## Dependencies

```
fastapi, uvicorn[standard], jinja2     # Web dashboard
httpx, python-binance                  # Data feeds
py-clob-client==0.34.4, web3, eth-account  # Polymarket execution
pydantic, aiosqlite, python-dotenv     # Core infrastructure
pytest, pytest-asyncio                 # Testing
```
