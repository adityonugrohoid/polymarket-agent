"""Prompt templates for the Council of Models."""

SENTIMENT_PROMPT = """Crypto market sentiment analyst. Classify the sentiment for this signal.

{symbol} | Price: ${price:,.2f} | Momentum: {momentum_pct:+.2f}% | Direction: {direction}
Odds: {odds_midpoint:.2f} | Fair: {implied_fair_odds:.2f} | Edge: {edge_pct:+.2f}%

Output exactly two lines, nothing else:
SENTIMENT: [BULLISH or BEARISH or NEUTRAL]
REASONING: [one sentence why]
"""

CONFIDENCE_PROMPT = """Crypto trade confidence grader. Rate if this opportunity is genuine or noise.

{symbol} | Price: ${price:,.2f} | Momentum: {momentum_pct:+.2f}%
Odds: {odds_midpoint:.2f} | Fair: {implied_fair_odds:.2f} | Edge: {edge_pct:+.2f}% | Score: {signal_score:.2f}
Sentiment: {sentiment} — {sentiment_reasoning}

Consider: edge vs 0.44% fees, momentum sustainability, sentiment alignment.

Output exactly two lines, nothing else:
CONFIDENCE: [number between 0.0 and 1.0]
REASONING: [one sentence why]
"""

TRADE_JUDGE_PROMPT = """Final trade judge. Decide TRADE or SKIP.

{symbol} | Price: ${price:,.2f} | Momentum: {momentum_pct:+.2f}%
Odds: {odds_midpoint:.2f} | Fair: {implied_fair_odds:.2f} | Edge: {edge_pct:+.2f}% | Score: {signal_score:.2f}
Sentiment: {sentiment} — {sentiment_reasoning}
Confidence: {confidence:.2f} — {confidence_reasoning}
Max size: ${max_position_size:.0f} | Available: ${available_capital:.0f} | Fees: ~0.44%

Output exactly three lines, nothing else:
DECISION: [TRADE or SKIP]
SIZE: [dollar amount between 5 and {max_position_size:.0f}, or 0 if SKIP]
REASONING: [one sentence why]
"""
