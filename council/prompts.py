"""Prompt templates for the Council of Models."""

SENTIMENT_PROMPT = """You are a crypto market sentiment analyst. Analyze the following market signal and determine the sentiment direction.

MARKET DATA:
- Symbol: {symbol}
- Current Price: ${price:,.2f}
- Price Momentum: {momentum_pct:+.2f}% (over recent window)
- Direction: {direction}
- Polymarket Odds (current): {odds_midpoint:.2f}
- Implied Fair Odds: {implied_fair_odds:.2f}
- Edge: {edge_pct:+.2f}%

Based on the price momentum and market dynamics, classify the sentiment:

Respond with EXACTLY one of: BULLISH, BEARISH, or NEUTRAL
Then on the next line, provide a brief 1-sentence reasoning.

Format:
SENTIMENT: <BULLISH|BEARISH|NEUTRAL>
REASONING: <your reasoning>
"""

CONFIDENCE_PROMPT = """You are a quantitative confidence grader for crypto prediction markets. Given the following signal and sentiment analysis, rate your confidence that this trade opportunity is genuine (not noise).

MARKET DATA:
- Symbol: {symbol}
- Current Price: ${price:,.2f}
- Price Momentum: {momentum_pct:+.2f}%
- Polymarket Odds: {odds_midpoint:.2f}
- Implied Fair Odds: {implied_fair_odds:.2f}
- Edge: {edge_pct:+.2f}%
- Signal Score: {signal_score:.2f}

SENTIMENT ANALYSIS:
- Sentiment: {sentiment}
- Reasoning: {sentiment_reasoning}

Rate your confidence from 0.0 (no confidence, likely noise) to 1.0 (very high confidence, clear mispricing).

Consider:
1. Is the edge large enough to overcome fees (0.44%)?
2. Is the momentum sustained or a blip?
3. Does the sentiment align with the price direction?

Respond with EXACTLY this format:
CONFIDENCE: <float 0.0-1.0>
REASONING: <your reasoning>
"""

TRADE_JUDGE_PROMPT = """You are the final trade judge for a crypto prediction market bot. You make the TRADE or SKIP decision.

MARKET DATA:
- Symbol: {symbol}
- Current Price: ${price:,.2f}
- Price Momentum: {momentum_pct:+.2f}%
- Polymarket Odds: {odds_midpoint:.2f}
- Implied Fair Odds: {implied_fair_odds:.2f}
- Edge: {edge_pct:+.2f}%
- Signal Score: {signal_score:.2f}

COUNCIL ANALYSIS:
- Sentiment: {sentiment}
- Sentiment Reasoning: {sentiment_reasoning}
- Confidence: {confidence:.2f}
- Confidence Reasoning: {confidence_reasoning}

RISK LIMITS:
- Max position size: ${max_position_size:.0f}
- Available capital: ${available_capital:.0f}
- Trading fees: ~0.44%

Make your decision. If TRADE, specify the dollar amount (between $5 and ${max_position_size:.0f}).

Respond with EXACTLY this format:
DECISION: <TRADE|SKIP>
SIZE: <dollar amount or 0>
REASONING: <your reasoning>
"""
