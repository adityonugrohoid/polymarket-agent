"""Wrapper around py-clob-client for authenticated Polymarket trading."""
import logging
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from eth_account import Account

logger = logging.getLogger(__name__)

CLOB_HOST = "https://clob.polymarket.com"


class PolymarketClient:
    """Authenticated Polymarket CLOB client for live trading."""

    def __init__(self, private_key: str, chain_id: int = 137):
        if not private_key:
            raise ValueError("POLYMARKET_PRIVATE_KEY is required for live trading")

        self.chain_id = chain_id
        self.account = Account.from_key(private_key)
        self.address = self.account.address

        self.client = ClobClient(
            host=CLOB_HOST,
            key=private_key,
            chain_id=chain_id,
        )

        # Derive API credentials
        self.client.set_api_creds(self.client.derive_api_key())

        logger.info(
            "Polymarket client initialized",
            extra={"address": self.address, "chain_id": chain_id},
        )

    def get_midpoint(self, token_id: str) -> Optional[float]:
        """Get current midpoint for a token."""
        try:
            resp = self.client.get_midpoint(token_id)
            return float(resp.get("mid", 0))
        except Exception as e:
            logger.error(f"Failed to get midpoint: {e}")
            return None

    def get_order_book(self, token_id: str) -> Optional[dict]:
        """Get order book for a token."""
        try:
            return self.client.get_order_book(token_id)
        except Exception as e:
            logger.error(f"Failed to get order book: {e}")
            return None

    def create_and_post_order(
        self,
        token_id: str,
        price: float,
        size: float,
        side: str,
    ) -> Optional[dict]:
        """Create and post a limit order.

        Args:
            token_id: The CLOB token ID
            price: Limit price (0-1 for binary markets)
            size: Number of shares (size_usd / price)
            side: "BUY" or "SELL"
        """
        try:
            order_args = OrderArgs(
                price=price,
                size=size,
                side=side,
                token_id=token_id,
            )
            signed_order = self.client.create_order(order_args)
            resp = self.client.post_order(signed_order, OrderType.GTC)

            logger.info(
                "Order posted",
                extra={
                    "token_id": token_id,
                    "side": side,
                    "price": price,
                    "size": size,
                    "response": str(resp)[:200],
                },
            )
            return resp
        except Exception as e:
            logger.error(f"Failed to post order: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        try:
            self.client.cancel(order_id)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False

    def get_open_orders(self) -> list:
        """Get all open orders."""
        try:
            return self.client.get_orders()
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return []
