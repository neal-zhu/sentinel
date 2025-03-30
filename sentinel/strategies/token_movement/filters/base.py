"""
Base filter class for the Token Movement Strategy.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
from sentinel.core.events import TokenTransferEvent

class BaseFilter(ABC):
    """
    Base class for all token movement filters.
    
    Filters are responsible for determining whether a token transfer event should
    be processed or ignored based on various criteria.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the filter with configuration parameters.
        
        Args:
            config: Configuration parameters for the filter
        """
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        
    @abstractmethod
    def should_filter(self, event: TokenTransferEvent, context: Dict[str, Any]) -> bool:
        """
        Determine if a token transfer event should be filtered (ignored).
        
        Args:
            event: The token transfer event to check
            context: Additional context information from the strategy
            
        Returns:
            bool: True if the event should be filtered out, False otherwise
        """
        pass
    
    def is_enabled(self) -> bool:
        """
        Check if this filter is enabled.
        
        Returns:
            bool: Whether the filter is enabled
        """
        return self.enabled
    
    def set_enabled(self, enabled: bool):
        """
        Enable or disable this filter.
        
        Args:
            enabled: Whether to enable the filter
        """
        self.enabled = enabled
