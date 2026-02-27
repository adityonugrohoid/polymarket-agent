"""Market discovery via Polymarket Gamma API."""
import json
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"


@dataclass
class DiscoveredMarket:
    """A Polymarket market matching our crypto filter."""
    condition_id: str
    token_id: str
    question: str
    outcome: str
    symbol: str  # mapped crypto symbol (btcusdt, ethusdt, solusdt)


# Keywords to map Polymarket questions to Binance symbols
# Use word boundaries via tuples: (keyword, must_not_contain)
CRYPTO_KEYWORDS = {
    "btcusdt": ["bitcoin", " btc ", " btc?", " btc."],
    "ethusdt": ["ethereum", " eth "],
    "solusdt": ["solana", " sol "],
}

# Broader keywords for event-level matching
CRYPTO_EVENT_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "solana", "sol",
    "crypto", "altcoin", "defi",
]


def _match_symbol(question: str) -> Optional[str]:
    """Match a market question to a Binance symbol."""
    q_lower = f" {question.lower()} "
    for symbol, keywords in CRYPTO_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            return symbol
    return None


class GammaDiscovery:
    """Discovers crypto-related Polymarket markets via Gamma API."""

    def __init__(self):
        self._markets: list[DiscoveredMarket] = []

    async def discover(self, limit: int = 200) -> list[DiscoveredMarket]:
        """Fetch active crypto markets from Gamma API.

        Strategy: fetch all active events, filter client-side for crypto keywords,
        then verify each token has an active CLOB orderbook.
        """
        self._markets = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch all active events and filter client-side
            try:
                resp = await client.get(
                    f"{GAMMA_BASE}/events",
                    params={
                        "active": "true",
                        "closed": "false",
                        "limit": limit,
                    },
                )
                resp.raise_for_status()
                events = resp.json()
            except httpx.HTTPError as e:
                logger.error(f"Gamma API error: {e}")
                return []

            # Filter for crypto-related events by text matching
            for event in events:
                title = event.get("title", "")
                desc = event.get("description", "")
                event_text = f"{title} {desc}".lower()

                if not any(kw in event_text for kw in CRYPTO_EVENT_KEYWORDS):
                    continue

                for market in event.get("markets", []):
                    question = market.get("question", "")
                    symbol = _match_symbol(question)
                    if not symbol:
                        # Try matching on event title if question doesn't match
                        symbol = _match_symbol(title)
                    if not symbol:
                        continue

                    condition_id = market.get("conditionId", "")
                    clob_tokens = market.get("clobTokenIds", "")
                    if isinstance(clob_tokens, str):
                        try:
                            clob_tokens = json.loads(clob_tokens)
                        except (json.JSONDecodeError, TypeError):
                            clob_tokens = []

                    outcomes = market.get("outcomes", "")
                    if isinstance(outcomes, str):
                        try:
                            outcomes = json.loads(outcomes)
                        except (json.JSONDecodeError, TypeError):
                            outcomes = []

                    for i, token_id in enumerate(clob_tokens):
                        outcome_name = outcomes[i] if i < len(outcomes) else f"outcome_{i}"
                        dm = DiscoveredMarket(
                            condition_id=condition_id,
                            token_id=token_id,
                            question=question,
                            outcome=outcome_name,
                            symbol=symbol,
                        )
                        self._markets.append(dm)

        # Deduplicate
        seen = set()
        unique = []
        for m in self._markets:
            key = (m.condition_id, m.token_id)
            if key not in seen:
                seen.add(key)
                unique.append(m)

        # Verify CLOB orderbook exists for each token
        verified = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            for m in unique:
                try:
                    resp = await client.get(
                        f"{CLOB_BASE}/midpoint",
                        params={"token_id": m.token_id},
                    )
                    if resp.status_code == 200:
                        mid = resp.json().get("mid", 0)
                        if float(mid) > 0:
                            verified.append(m)
                            logger.info(
                                "Verified market",
                                extra={
                                    "question": m.question[:80],
                                    "outcome": m.outcome,
                                    "midpoint": mid,
                                    "symbol": m.symbol,
                                },
                            )
                except httpx.HTTPError:
                    continue

        self._markets = verified
        logger.info(
            "Discovery complete",
            extra={"found": len(unique), "verified": len(verified)},
        )
        return self._markets

    @property
    def markets(self) -> list[DiscoveredMarket]:
        return self._markets
