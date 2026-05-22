<div align="center">

# Polymarket AI Trading Agent

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Autonomous crypto trading agent: detects Binance vs Polymarket price divergences, runs a 3-LLM council to decide each trade.**

[Getting Started](#getting-started) | [Usage](#usage) | [Architecture](#architecture)

</div>

---

## Table of Contents

- [The Problem](#the-problem)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [API Reference](#api-reference)
- [Architectural Decisions](#architectural-decisions)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Related Projects](#related-projects)
- [License](#license)
- [Author](#author)

## The Problem

### Arbitrage between spot and prediction markets

Binance spot prices and Polymarket prediction-market odds track the same underlying assets but update through different mechanisms and at different speeds. When the two diverge by more than transaction costs, a short-lived arbitrage window opens. Identifying those windows reliably requires continuous data correlation, dynamic threshold logic, and a decision layer that can reason about signal quality rather than just trigger mechanically on raw edge size.

### The Solution

This agent connects both feeds in real time, scores each divergence signal across three weighted dimensions (edge, momentum, volume), then hands each qualifying signal to a sequential council of three LLMs. Each model has one tightly scoped job: sentiment classification, confidence grading, and final TRADE/SKIP sizing. A short-circuit rule drops the most expensive call when confidence is low, making the council practical at runtime latencies.

## Features

- **Real-time divergence detection** between Binance spot prices and Polymarket prediction-market odds
- **Council of 3 LLMs** (sentiment, confidence grader, trade judge) with structured reasoning logged for every decision
- **Thinking-mode support** for reasoning models: parsers use last-match strategy to skip echoed prompt content in extended thinking traces
- **Short-circuit logic** skips the trade-judge call when confidence is below threshold, cutting average per-signal LLM cost significantly
- **Risk management** with per-trade limits, portfolio caps, and per-symbol cooldowns enforced before every execution
- **Paper trading by default** with the full trade lifecycle (signal, council reasoning, fill, P&L) logged to SQLite
- **Simulation mode** with synthetic markets and a deliberately lagged price feed so the full pipeline runs end-to-end without live API keys
- **FastAPI dashboard** on `:8081` for real-time monitoring of trades and P&L
- **Async-first** via `asyncio` throughout, from feed ingestion to trade logging

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.12+ |
| Runtime | `asyncio` event loop |
| LLM client | Ollama (cloud or local) |
| Sentiment model | `nemotron-3-nano:30b` |
| Confidence grader | `qwen3-next:80b` |
| Trade judge | `gpt-oss:120b` |
| Price feed | Binance WebSocket |
| Odds feed | Polymarket CLOB midpoint API |
| Storage | SQLite via `aiosqlite` |
| Config | Pydantic settings |
| Dashboard | FastAPI on `:8081` |
| Tests | `pytest`, `pytest-asyncio` |
| Dependencies | `requirements.txt` |

## Architecture

```mermaid
graph TD
    subgraph Feeds
        B["Binance WebSocket<br/>(or SimulatedPriceFeed)"]
        P["Polymarket CLOB<br/>(or SimulatedOddsFeed)"]
    end

    B -->|price_queue| FA["FeedAggregator<br/>pairs prices + odds by symbol"]
    P -->|odds_queue| FA

    FA -->|paired_queue| DD["DivergenceDetector<br/>momentum + implied odds + edge + score"]

    DD -->|signal_queue| S["SentimentAgent<br/>nemotron-3-nano:30b"]

    subgraph Council["Council of Models"]
        S -->|SentimentResult| C["ConfidenceGrader<br/>qwen3-next:80b"]
        C -->|"confidence >= threshold"| J["TradeJudge<br/>gpt-oss:120b"]
        C -->|"confidence < threshold"| SKIP["Short-circuit SKIP"]
    end

    J -->|TradeVerdict| EX["Execution<br/>PaperTrader / OrderManager<br/>risk checks, fill, log"]
    SKIP -.->|no trade| EX

    EX --> DB[("SQLite<br/>trades + signals")]
    DB --> DASH["FastAPI Dashboard<br/>:8081"]

    style Feeds fill:#0f3460,stroke:#16213e,stroke-width:1px,color:#fff
    style Council fill:#16213e,stroke:#0f3460,stroke-width:2px,color:#fff
    style B fill:#0f3460,color:#fff
    style P fill:#0f3460,color:#fff
    style FA fill:#16213e,color:#fff
    style DD fill:#16213e,color:#fff
    style S fill:#533483,color:#fff
    style C fill:#533483,color:#fff
    style J fill:#533483,color:#fff
    style SKIP fill:#16213e,color:#fff
    style EX fill:#0f3460,color:#fff
    style DB fill:#16213e,color:#fff
    style DASH fill:#16213e,color:#fff
```

## Getting Started

### Prerequisites

- Python 3.12+
- [Ollama](https://ollama.com) API key (cloud) or a local Ollama instance
- Binance WebSocket access (optional: set `SIMULATION_MODE=true` to run without any external creds)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/adityonugrohoid/polymarket-agent.git
   cd polymarket-agent
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Configuration

```bash
cp .env.example .env
```

Edit `.env` with your settings:

<details>
<summary>Full configuration reference</summary>

```bash
# -- Trading ------------------------------------------
TRADING_MODE=paper                    # paper or live
BINANCE_SYMBOLS=btcusdt,ethusdt,solusdt

# -- LLM (Ollama Cloud or local) ----------------------
OLLAMA_HOST=https://ollama.com        # or http://localhost:11434
OLLAMA_API_KEY=your_key_here
LLM_MODEL_SENTIMENT=nemotron-3-nano:30b
LLM_MODEL_GRADER=qwen3-next:80b
LLM_MODEL_JUDGE=gpt-oss:120b

# -- Strategy Thresholds ------------------------------
MIN_EDGE_PCT=0.5                      # Minimum mispricing % to trigger signal
MIN_SIGNAL_SCORE=0.15                 # Minimum composite score (0-1)
MIN_CONFIDENCE=0.3                    # LLM confidence threshold for trade judge

# -- Risk Management ----------------------------------
MAX_CAPITAL=1000                      # Total portfolio cap ($)
MAX_POSITION_SIZE=50                  # Per-trade limit ($)
MAX_OPEN_POSITIONS=3                  # Max concurrent positions
COOLDOWN_SECONDS=30                   # Per-symbol cooldown after trade

# -- Simulation ---------------------------------------
SIMULATION_MODE=true                  # Use synthetic feeds
SIM_MARKETS_PER_SYMBOL=3
SIM_STRIKE_SPREAD_PCT=1.0
SIM_PRICE_LAG_SECONDS=5.0
SIM_NOISE_PCT=2.0
SIM_ODDS_INTERVAL=1.0

# -- Infrastructure -----------------------------------
DASHBOARD_PORT=8081
DB_PATH=data/trades.db
```

</details>

## Usage

```bash
# Start the agent (paper trading + simulation by default)
python agent.py

# Dashboard at http://localhost:8081
```

Example council evaluation cycle from a simulation run:

```
Signal: BTCUSDT | $89,086 | Momentum: +2.22% | Edge: +6.67% | Score: 0.47 | UP

  Sentiment  (nemotron, 1554ms)  -> BULLISH
    "The upward momentum and positive edge indicate a bullish outlook."

  Confidence (qwen3, 15063ms)    -> 0.47
    "Score below 0.5 indicates low confidence due to momentum
     sustainability concerns despite positive edge."

  Trade Judge (gpt-oss, 1801ms)  -> SKIP, $0
```

When the judge decides to trade:

```
Signal: BTCUSDT | $87,822 | Momentum: +0.94% | Edge: +6.58% | Score: 0.46 | UP

  Sentiment  -> BULLISH
  Confidence -> 0.46
  Trade Judge -> TRADE, $10
    "Positive edge (+6.58%) suggests a favorable expected value despite
     low confidence, so a modest $10 position limits risk while
     capturing upside."

  Paper trade executed: BUY btcusdt $10.00 @ 0.5096
```

## How It Works

### 1. Data Feeds

- **Binance WebSocket** streams real-time prices for BTC, ETH, SOL with a rolling 20-tick momentum window
- **Polymarket CLOB** polls prediction-market odds every 5s via the midpoint API
- **FeedAggregator** pairs each price tick with the latest odds for the same symbol before passing to the strategy layer

### 2. Divergence Detection

The strategy layer (`strategy/divergence_detector.py`) computes:

| Metric | Formula | Description |
|--------|---------|-------------|
| Implied fair odds | `market_odds + (momentum * 0.03)` | 1% price move adjusts odds by 3% |
| Edge | `implied_fair - market_odds` | The mispricing percentage |
| Composite score | `edge*0.5 + momentum*0.3 + volume*0.2` | Weighted signal strength (0-1) |

Signals fire when `edge > MIN_EDGE_PCT` and `score > MIN_SIGNAL_SCORE`.

### 3. Council of Models

Three LLMs evaluate each signal sequentially via `council/orchestrator.py`:

| # | Agent | Model | Role | Latency |
|---|-------|-------|------|---------|
| 1 | Sentiment | `nemotron-3-nano:30b` | Classify BULLISH / BEARISH / NEUTRAL | ~1.5s |
| 2 | Confidence | `qwen3-next:80b` | Grade signal quality 0.0-1.0 | ~12-20s |
| 3 | Trade Judge | `gpt-oss:120b` | Final TRADE/SKIP + position sizing | ~2s |

Short-circuit: if confidence falls below `MIN_CONFIDENCE`, the trade judge is skipped entirely, dropping average per-signal LLM cost significantly.

Thinking-mode support: all parsers handle models using extended thinking output (`think=True`). When both the response field and the thinking field contain candidates, the parser takes the last match to avoid echoed prompt content.

### 4. Execution

| Mode | Status | Description |
|------|--------|-------------|
| Paper | Active (default) | Simulates fills at market midpoint; logs to SQLite with full council reasoning |
| Live | Scaffolded | `OrderManager` + `PolymarketClient` for authenticated CLOB orders on Polygon |

### 5. Risk Management

Enforced at the execution layer via `execution/position_tracker.py` before every trade:

| Control | Default | Description |
|---------|---------|-------------|
| `MAX_OPEN_POSITIONS` | 3 | Max concurrent positions |
| `MAX_POSITION_SIZE` | $50 | Per-trade limit |
| `MAX_CAPITAL` | $1,000 | Total portfolio exposure cap |
| `COOLDOWN_SECONDS` | 30 | Per-symbol cooldown after trade |

### 6. Simulation Mode

Polymarket currently has no short-term crypto price markets (only long-dated events like "BTC hits $150k by June 2026"), so the agent ships with a full simulation layer at `feeds/simulation.py`.

Set `SIMULATION_MODE=true` to activate:

| Component | Description |
|-----------|-------------|
| `SimulatedMarketGenerator` | Creates synthetic 15-min markets at 3 strike levels per symbol (-1%, 0%, +1%) |
| `SimulatedOddsFeed` | Computes odds from a deliberately lagged price buffer (5s lag creates divergence) |
| `SimulatedPriceFeed` | Gaussian random walk (mean +0.08%, stddev 1.2% per tick) |

Odds formula:
```python
distance = (lagged_price - strike) / strike
raw_odds = 0.5 + (distance * 10)          # 1% above strike -> 0.6 odds
odds = clamp(raw_odds + noise, 0.05, 0.95)
```

## API Reference

The FastAPI dashboard (`dashboard/main.py`) exposes three read-only JSON endpoints for programmatic monitoring.

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/status` | Agent status, P&L summary, open position count |
| `GET` | `/api/trades` | Recent trades (default: last 50; `?limit=N` to override) |
| `GET` | `/api/pnl` | P&L summary object |

### Example Request

```bash
curl http://localhost:8081/api/status
```

### Example Response

```json
{
  "status": "running",
  "pnl": { "total_pnl": 12.40, "win_rate": 0.62 },
  "open_positions": 1
}
```

## Architectural Decisions

### 1. Council of three specialized models, not one general-purpose call

**Decision:** Pipeline three smaller, specialized models (sentiment, confidence grader, trade judge) rather than a single large general-purpose call.

**Reasoning:** Each model has a tight, easy-to-evaluate output schema (single label, single float, TRADE+size). Concatenating their reasoning into the trade record makes per-decision auditing straightforward. The cost is latency across three round-trips, mitigated by the short-circuit when confidence is low.

### 2. Short-circuit before the expensive trade judge

**Decision:** Skip the trade-judge call entirely when the confidence grader returns below `MIN_CONFIDENCE`.

**Reasoning:** The judge (`gpt-oss:120b`) is the slowest of the three models. Most signals never clear the confidence bar - gating eliminates the dominant-cost call on the dominant case, dropping average per-signal LLM cost by roughly an order of magnitude.

### 3. Last-match parsing for thinking-mode models

**Decision:** When parsing responses from reasoning models that emit extended thinking text, the parser scans the full text and takes the last match.

**Reasoning:** Reasoning models often echo earlier prompt content or intermediate hypotheses inside their thinking trace. Taking the last match correlates strongly with the model's final decision and sidesteps a class of brittle regex-anchoring bugs encountered during development.

### 4. Simulation mode as a first-class build target

**Decision:** Ship a complete synthetic feed and market layer that runs the full pipeline without external APIs.

**Reasoning:** Polymarket has no short-term crypto markets today, so the live target is a future state. Simulation lets development, tests, and CI exercise the whole council and execution flow now, with one config flag rather than a separate harness.

## Project Structure

```
polymarket-agent/
├── agent.py                        # Main entry point - wires all components
│
├── feeds/                          # Data ingestion layer
│   ├── binance_ws.py               #   Binance WebSocket price streaming
│   ├── polymarket_odds.py          #   CLOB midpoint polling
│   ├── gamma_discovery.py          #   Market discovery via Gamma API
│   ├── feed_aggregator.py          #   Pairs price ticks with odds
│   └── simulation.py               #   Synthetic markets, odds, and prices
│
├── strategy/                       # Signal generation layer
│   ├── divergence_detector.py      #   Core divergence detection algorithm
│   ├── signal.py                   #   Composite signal scoring
│   └── thresholds.py               #   Default strategy constants
│
├── council/                        # LLM decision layer
│   ├── orchestrator.py             #   3-agent pipeline with short-circuit
│   ├── sentiment_agent.py          #   Agent 1: sentiment classification
│   ├── confidence_grader.py        #   Agent 2: confidence scoring 0-1
│   ├── trade_judge.py              #   Agent 3: final TRADE/SKIP decision
│   └── prompts.py                  #   Prompt templates
│
├── execution/                      # Trade execution layer
│   ├── paper_trader.py             #   Simulated trade execution
│   ├── order_manager.py            #   Live Polymarket CLOB orders
│   ├── polymarket_client.py        #   Authenticated CLOB client
│   └── position_tracker.py         #   Risk limits enforcement
│
├── storage/                        # Persistence layer
│   ├── db.py                       #   Async SQLite wrapper (aiosqlite)
│   └── models.py                   #   Table schemas
│
├── shared/                         # Shared utilities
│   ├── config.py                   #   Environment config (Pydantic)
│   ├── schemas.py                  #   Pipeline data models
│   ├── ollama_client.py            #   LLM client with thinking-mode support
│   └── logging.py                  #   Structured JSON logging
│
├── dashboard/                      # Web monitoring
│   ├── main.py                     #   FastAPI dashboard + JSON API endpoints
│   └── templates/index.html        #   Dashboard template
│
├── tests/                          # Test suite
├── .env.example                    # Configuration template
└── requirements.txt                # Python dependencies
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -q

# Run with verbose output
python -m pytest tests/ -v

# Run specific module
python -m pytest tests/test_simulation.py -v
```

| Module | Tests | Coverage |
|--------|-------|----------|
| Divergence detector | 5 | Signal generation, thresholds |
| Feed aggregator | 3 | Price+odds pairing |
| Sentiment agent | 4 | BULLISH/BEARISH/NEUTRAL parsing |
| Confidence grader | 4 | Float 0-1 parsing, clamping |
| Trade judge | 4 | TRADE/SKIP + size parsing |
| Orchestrator | 4 | Full pipeline, short-circuit |
| Paper trader | 5 | Execution, risk limits, P&L |
| Simulation | 11 | Market gen, odds lag, random walk |
| Signal scoring | 6 | Edge, momentum, volume, composite |
| Config | 3 | Env loading |

## License

This project is licensed under the [MIT License](LICENSE).

## Author

**Adityo Nugroho** ([@adityonugrohoid](https://github.com/adityonugrohoid))
