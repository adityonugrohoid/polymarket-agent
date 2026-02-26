"""Market discovery via Polymarket Gamma API."""
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"


@dataclass
class DiscoveredMarket:
    """A Polymarket market matching our crypto filter."""
    condition_id: str
    token_id: str
    question: str
    outcome: str
    symbol: str  # mapped crypto symbol (btcusdt, ethusdt, solusdt)


# Keywords to map Polymarket questions to Binance symbols
CRYPTO_KEYWORDS = {
    "btcusdt": ["bitcoin", "btc"],
    "ethusdt": ["ethereum", "eth"],
    "solusdt": ["solana", "sol"],
}


def _match_symbol(question: str) -> Optional[str]:
    """Match a market question to a Binance symbol."""
    q_lower = question.lower()
    for symbol, keywords in CRYPTO_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            return symbol
    return None


class GammaDiscovery:
    """Discovers crypto-related Polymarket markets via Gamma API."""

    def __init__(self):
        self._markets: list[DiscoveredMarket] = []

    async def discover(self, limit: int = 100) -> list[DiscoveredMarket]:
        """Fetch active crypto markets from Gamma API."""
        self._markets = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Search for crypto-related events
            for tag in ["crypto", "bitcoin", "ethereum", "solana"]:
                try:
                    resp = await client.get(
                        f"{GAMMA_BASE}/events",
                        params={
                            "tag": tag,
                            "active": "true",
                            "closed": "false",
                            "limit": limit,
                        },
                    )
                    resp.raise_for_status()
                    events = resp.json()

                    for event in events:
                        for market in event.get("markets", []):
                            question = market.get("question", "")
                            symbol = _match_symbol(question)
                            if not symbol:
                                continue

                            condition_id = market.get("conditionId", "")
                            # clobTokenIds is a JSON string: '["id1","id2"]'
                            clob_tokens = market.get("clobTokenIds", "")
                            if isinstance(clob_tokens, str):
                                import json
                                try:
                                    clob_tokens = json.loads(clob_tokens)
                                except (json.JSONDecodeError, TypeError):
                                    clob_tokens = []

                            for i, token_id in enumerate(clob_tokens):
                                outcome = market.get("outcomes", "")
                                if isinstance(outcome, str):
                                    try:
                                        outcome = json.loads(outcome)
                                    except (json.JSONDecodeError, TypeError):
                                        outcome = []
                                outcome_name = outcome[i] if i < len(outcome) else f"outcome_{i}"

                                dm = DiscoveredMarket(
                                    condition_id=condition_id,
                                    token_id=token_id,
                                    question=question,
                                    outcome=outcome_name,
                                    symbol=symbol,
                                )
                                self._markets.append(dm)

                except httpx.HTTPError as e:
                    logger.warning(f"Gamma API error for tag={tag}: {e}")
                    continue

        # Deduplicate by condition_id + token_id
        seen = set()
        unique = []
        for m in self._markets:
            key = (m.condition_id, m.token_id)
            if key not in seen:
                seen.add(key)
                unique.append(m)
        self._markets = unique

        logger.info(
            "Discovered markets",
            extra={"count": len(self._markets)},
        )
        return self._markets

    @property
    def markets(self) -> list[DiscoveredMarket]:
        return self._markets
