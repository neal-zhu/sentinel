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
        super().__init__(config)  # 父类已经处理了None情况，直接传递即可
        # 从配置中获取require_significant标志，默认为False表示过滤所有简单转账
        self.require_significant = self.config.get("require_significant", False)

    def should_filter(self, event: TokenTransferEvent, context: Dict[str, Any]) -> bool:
        """
        Determine if a simple ERC20 transfer should be filtered out.

        Args:
            event: The token transfer event to check
            context: Additional context information from the strategy

        Returns:
            bool: True if the event should be filtered out, False otherwise
        """
        # 1. 始终处理被监视的地址或代币的转账（保证测试用例通过）
        if (
            context.get("is_watched_from", False)
            or context.get("is_watched_to", False)
            or context.get("is_watched_token", False)
        ):
            return False

        # 2. 如果有合约交互，可能是DEX交易或其他有趣的活动，不过滤
        if event.has_contract_interaction:
            return False

        # 3. 检查发送方和接收方是否都是普通地址（非合约）
        is_from_contract = AddressUtils.is_contract_address(
            event.from_address, context.get("known_dexes", {})
        )
        is_to_contract = AddressUtils.is_contract_address(
            event.to_address, context.get("known_dexes", {})
        )

        # 4. 如果发送方和接收方都是普通地址（EOA之间的直接转账）
        if not (is_from_contract or is_to_contract):
            # 如果需要考虑金额是否显著
            if self.require_significant:
                is_significant = context.get("is_significant_transfer", False)
                if not is_significant:
                    logger.debug(
                        f"Filtering non-significant EOA-to-EOA transfer: {event.transaction_hash}"
                    )
                    return True
                return False  # 显著金额的转账不过滤
            else:
                # 不考虑金额直接过滤所有EOA到EOA转账
                logger.debug(
                    f"Filtering direct EOA-to-EOA transfer: {event.transaction_hash}"
                )
                return True

        # 其他情况不过滤
        return False
