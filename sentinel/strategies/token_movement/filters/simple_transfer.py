"""
Simple transfer filter for the Token Movement Strategy.
"""
from typing import Any, Dict, Optional

from sentinel.core.events import TokenTransferEvent
from sentinel.logger import logger
from sentinel.strategies.token_movement.filters.base import BaseFilter
from sentinel.strategies.token_movement.utils.address_utils import AddressUtils


class SimpleTransferFilter(BaseFilter):
    """
    Filter for simple ERC20 transfers that are directly between EOAs.

    This filter identifies and filters out direct transfers between EOAs (Externally Owned Accounts)
    without contract interactions, which are unlikely to be interesting for trading/arbitrage purposes.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the simple transfer filter.

        Args:
            config: Configuration parameters for the filter
        """
        super().__init__(config)

    def should_filter(self, event: TokenTransferEvent, context: Dict[str, Any]) -> bool:
        """
        Determine if a simple ERC20 transfer should be filtered out.

        Args:
            event: The token transfer event to check
            context: Additional context information from the strategy

        Returns:
            bool: True if the event should be filtered out, False otherwise
        """
        # 1. 如果有合约交互，可能是DEX交易或其他有趣的活动，不过滤
        if event.has_contract_interaction:
            return False

        # 2. 检查发送方和接收方是否都是普通地址（非合约）
        is_from_contract = AddressUtils.is_contract_address(
            event.from_address, context.get("known_dexes", {})
        )
        is_to_contract = AddressUtils.is_contract_address(
            event.to_address, context.get("known_dexes", {})
        )

        # 3. 如果发送方和接收方都是普通地址（EOA之间的直接转账），过滤掉
        if not (is_from_contract or is_to_contract):
            logger.debug(
                f"Filtering direct EOA-to-EOA transfer: {event.transaction_hash}"
            )
            return True

        # 其他情况不过滤
        return False
