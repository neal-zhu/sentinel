"""
DEX trade filter for the Token Movement Strategy.
"""
from typing import Dict, Any, List
from sentinel.core.events import TokenTransferEvent
from sentinel.strategies.token_movement.filters.base import BaseFilter
from sentinel.strategies.token_movement.utils.address_utils import AddressUtils
from sentinel.strategies.token_movement.utils.token_utils import TokenUtils
from sentinel.logger import logger

class DexTradeFilter(BaseFilter):
    """
    Filter for identifying DEX trades.
    
    This filter identifies transfers that are likely part of DEX trades.
    It can be used either to filter out DEX trades (to reduce noise) or
    to specifically focus on DEX trades (for arbitrage detection).
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the DEX trade filter.
        
        Args:
            config: Configuration parameters for the filter
        """
        super().__init__(config)
        self.filter_dex_trades = self.config.get('filter_dex_trades', False)
        self.only_dex_trades = self.config.get('only_dex_trades', False)
        
    def is_likely_dex_trade(self, event: TokenTransferEvent, context: Dict[str, Any]) -> bool:
        """
        Check if a transfer is likely part of a DEX trade.
        
        Args:
            event: The token transfer event to check
            context: Additional context information from the strategy
            
        Returns:
            bool: Whether this appears to be a DEX trade
        """
        # If either address is a known DEX, it's likely a DEX trade
        whitelist_addresses = context.get('whitelist_addresses', {})
        if (AddressUtils.is_whitelisted_address(event.chain_id, event.from_address, whitelist_addresses) or
            AddressUtils.is_whitelisted_address(event.chain_id, event.to_address, whitelist_addresses)):
            return True
            
        # If the transaction has contract interaction, and one of the addresses is likely a contract,
        # it's more likely to be a DEX trade
        if event.has_contract_interaction:
            known_dexes = context.get('known_dexes', {})
            if (AddressUtils.is_contract_address(event.from_address, known_dexes) or 
                AddressUtils.is_contract_address(event.to_address, known_dexes)):
                return True
                
        # Check for common DEX patterns
        # 1. Round number transfers (common in swaps)
        value = event.formatted_value
        is_round_number = (value == int(value) or 
                          abs(value - round(value, 1)) < 0.01 or
                          abs(value - round(value, -1)) < 1)
            
        # 2. Common swap amounts like 0.1, 1, 10, 100, etc.
        common_swap_amounts = [0.1, 0.5, 1, 5, 10, 50, 100, 500, 1000]
        is_common_amount = any(abs(value - amt) / amt < 0.05 for amt in common_swap_amounts if amt > 0)
        
        # 3. Check if the token is a common DEX pair token
        is_common_token = False
        if event.token_symbol:
            is_common_token = TokenUtils.is_common_dex_token(event.token_symbol)
        
        # If it meets multiple criteria, it's likely a DEX trade
        return (is_round_number and is_common_amount) or (is_common_token and (is_round_number or is_common_amount))
        
    def should_filter(self, event: TokenTransferEvent, context: Dict[str, Any]) -> bool:
        """
        Determine if a transfer should be filtered based on whether it's a DEX trade.
        
        Args:
            event: The token transfer event to check
            context: Additional context information from the strategy
            
        Returns:
            bool: True if the event should be filtered out, False otherwise
        """
        # Always process transfers involving watched addresses/tokens
        if (context.get('is_watched_from', False) or
            context.get('is_watched_to', False) or
            context.get('is_watched_token', False)):
            return False
            
        is_dex_trade = self.is_likely_dex_trade(event, context)
        
        # Update context with this information for other components
        context['is_dex_trade'] = is_dex_trade
        
        # If we only want DEX trades, filter out non-DEX trades
        if self.only_dex_trades and not is_dex_trade:
            logger.debug(f"Filtering non-DEX trade: {event.transaction_hash}")
            return True
            
        # If we want to filter out DEX trades, filter them
        if self.filter_dex_trades and is_dex_trade:
            logger.debug(f"Filtering DEX trade: {event.transaction_hash}")
            return True
            
        return False
