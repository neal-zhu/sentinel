"""
Whitelist filter for the Token Movement Strategy.
"""
from typing import Any, Dict

from sentinel.core.events import TokenTransferEvent
from sentinel.logger import logger
from sentinel.strategies.token_movement.filters.base import BaseFilter
from sentinel.strategies.token_movement.utils.address_utils import AddressUtils


class WhitelistFilter(BaseFilter):
    """
    Filter for transfers involving whitelisted addresses.

    This filter identifies and filters out transfers involving addresses that are known
    to be legitimate (DEXes, exchanges, etc.) and generate a lot of normal transaction noise.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the whitelist filter.

        Args:
            config: Configuration parameters for the filter
        """
        super().__init__(config)
        self.whitelist_addresses = self.config.get("whitelist_addresses", {})

    def should_filter(self, event: TokenTransferEvent, context: Dict[str, Any]) -> bool:
        """
        Determine if a transfer involving whitelisted addresses should be filtered out.

        Args:
            event: The token transfer event to check
            context: Additional context information from the strategy

        Returns:
            bool: True if the event should be filtered out, False otherwise
        """
        # Always process transfers involving watched addresses/tokens
        if (
            context.get("is_watched_from", False)
            or context.get("is_watched_to", False)
            or context.get("is_watched_token", False)
        ):
            return False

        # Always process transfers that involve contract interactions (likely arbitrage or DEX trades)
        if event.has_contract_interaction:
            return False

        # Filter out transfers involving whitelisted addresses
        is_from_whitelisted = AddressUtils.is_whitelisted_address(
            event.chain_id, event.from_address, self.whitelist_addresses
        )

        is_to_whitelisted = AddressUtils.is_whitelisted_address(
            event.chain_id, event.to_address, self.whitelist_addresses
        )

        if is_from_whitelisted or is_to_whitelisted:
            logger.debug(
                f"Filtering transfer involving whitelisted address: {event.transaction_hash}"
            )
            return True

        return False
