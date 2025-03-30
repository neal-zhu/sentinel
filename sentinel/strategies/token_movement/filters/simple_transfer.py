"""
Simple transfer filter for the Token Movement Strategy.
"""
from typing import Dict, Any
from sentinel.core.events import TokenTransferEvent
from sentinel.strategies.token_movement.filters.base import BaseFilter
from sentinel.strategies.token_movement.utils.address_utils import AddressUtils
from sentinel.logger import logger

class SimpleTransferFilter(BaseFilter):
    """
    Filter for simple ERC20 transfers that are unlikely to be arbitrage.
    
    This filter identifies and filters out direct transfers between EOAs (Externally Owned Accounts)
    that are not significant in value and don't involve contract interactions.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the simple transfer filter.
        
        Args:
            config: Configuration parameters for the filter
        """
        super().__init__(config)
        self.require_significant = self.config.get('require_significant', True)
        
    def should_filter(self, event: TokenTransferEvent, context: Dict[str, Any]) -> bool:
        """
        Determine if a simple ERC20 transfer should be filtered out.
        
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
            
        # Always process transfers that involve contract interactions (likely arbitrage or DEX trades)
        if event.has_contract_interaction:
            return False
            
        # Check if this is a direct transfer between EOAs (not contracts)
        is_from_contract = AddressUtils.is_contract_address(
            event.from_address, 
            context.get('known_dexes', {})
        )
        is_to_contract = AddressUtils.is_contract_address(
            event.to_address, 
            context.get('known_dexes', {})
        )
        
        # If both addresses are likely EOAs (not contracts), this is probably a simple transfer
        is_likely_eoa_transfer = not (is_from_contract or is_to_contract)
        
        # If it's a simple transfer and not a significant amount, filter it
        if is_likely_eoa_transfer and self.require_significant:
            is_significant = context.get('is_significant_transfer', False)
            if not is_significant:
                logger.debug(f"Filtering simple ERC20 transfer between EOAs: {event.transaction_hash}")
                return True
                
        return False
