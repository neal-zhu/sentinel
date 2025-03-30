"""
Small transfer filter for the Token Movement Strategy.
"""
from typing import Dict, Any, Tuple
from sentinel.core.events import TokenTransferEvent
from sentinel.strategies.token_movement.filters.base import BaseFilter
from sentinel.logger import logger

class SmallTransferFilter(BaseFilter):
    """
    Filter for small token transfers.
    
    This filter identifies and filters out transfers that are too small to be of interest,
    based on historical statistics for the token.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the small transfer filter.
        
        Args:
            config: Configuration parameters for the filter
        """
        super().__init__(config)
        self.filter_small_transfers = self.config.get('filter_small_transfers', True)
        self.small_transfer_threshold = self.config.get('small_transfer_threshold', 0.1)
        self.min_stats_count = self.config.get('min_stats_count', 100)
        
    def should_filter(self, event: TokenTransferEvent, context: Dict[str, Any]) -> bool:
        """
        Determine if a small transfer should be filtered out.
        
        Args:
            event: The token transfer event to check
            context: Additional context information from the strategy
            
        Returns:
            bool: True if the event should be filtered out, False otherwise
        """
        # Skip if filtering is disabled
        if not self.filter_small_transfers:
            return False
            
        # Always process transfers involving watched addresses/tokens
        if (context.get('is_watched_from', False) or
            context.get('is_watched_to', False) or
            context.get('is_watched_token', False)):
            return False
            
        # Get token statistics from context
        token_stats = context.get('token_stats', {})
        token_key = (event.chain_id, event.token_address or 'native')
        stats = token_stats.get(token_key, {})
        
        # If we have stats for this token and enough data points
        if stats and 'avg_transfer' in stats and stats.get('transfer_count', 0) > self.min_stats_count:
            avg_transfer = stats['avg_transfer']
            
            # Filter out transfers that are too small (less than threshold % of average)
            if event.formatted_value < (avg_transfer * self.small_transfer_threshold):
                logger.debug(f"Filtering small transfer: {event.formatted_value} {event.token_symbol or 'tokens'} (avg: {avg_transfer})")
                return True
                
        return False
