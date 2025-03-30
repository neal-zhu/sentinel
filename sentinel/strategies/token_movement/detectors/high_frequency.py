"""
High frequency trading detector for the Token Movement Strategy.
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
from sentinel.core.events import TokenTransferEvent
from sentinel.core.alerts import Alert
from sentinel.strategies.token_movement.detectors.base import BaseDetector
from sentinel.strategies.token_movement.utils.chain_info import ChainInfo
from sentinel.logger import logger

class HighFrequencyDetector(BaseDetector):
    """
    Detector for high frequency trading activity.
    
    This detector identifies addresses that are making a large number of transfers
    in a short time period, which may indicate algorithmic trading or arbitrage.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the high frequency trading detector.
        
        Args:
            config: Configuration parameters for the detector
        """
        super().__init__(config)
        self.threshold = self.config.get('threshold', 20)  # Default: 20 transfers per window
        self.window_minutes = self.config.get('window_minutes', 30)  # Default: 30 minute window
        
    async def detect(self, event: TokenTransferEvent, context: Dict[str, Any]) -> List[Alert]:
        """
        Detect high frequency trading and generate alerts.
        
        Args:
            event: The token transfer event to analyze
            context: Additional context information
            
        Returns:
            List[Alert]: List of alerts generated, if any
        """
        alerts = []
        chain_id = event.chain_id
        block_number = event.block_number
        
        # Get address transfers by block from context
        address_transfers_by_block = context.get('address_transfers_by_block', {})
        last_checked_block = context.get('last_checked_block', {})
        
        # Check if we've already analyzed this block
        if chain_id in last_checked_block and last_checked_block[chain_id] >= block_number:
            return []
            
        # Update last checked block in context
        if 'last_checked_block' in context:
            context['last_checked_block'][chain_id] = block_number
        
        # Define high frequency window based on block times
        # For example, 100 blocks on Ethereum (~25 min), 500 on BSC (~25 min)
        window_seconds = self.window_minutes * 60
        high_frequency_window_blocks = ChainInfo.estimate_blocks_from_time(chain_id, window_seconds)
        
        # Calculate block window for analysis
        start_block = max(0, block_number - high_frequency_window_blocks)
        
        # Calculate address-specific frequency
        address_key = (chain_id, event.from_address)
        address_transfers = sum(
            count for blk, count in address_transfers_by_block.get(address_key, {}).items()
            if start_block <= blk <= block_number
        )
        
        # Estimate time for window in hours
        window_hours = window_seconds / 3600  # Convert to hours
        
        # If this is a high frequency trading pattern
        if address_transfers >= self.threshold:
            result = {
                'address': event.from_address,
                'transfer_count': address_transfers,
                'time_frame': high_frequency_window_blocks,
                'time_frame_hours': window_hours,
                'threshold': self.threshold,
                'is_high_frequency': True
            }
            
            logger.info(f"High-frequency trading detected for address {event.from_address}: {address_transfers} transfers in {high_frequency_window_blocks} blocks")
            
            alerts.append(Alert(
                title="High-Frequency Trading Detected",
                description=f"Address {event.from_address} has made {address_transfers} transfers in {high_frequency_window_blocks} blocks (~{window_hours:.1f} hours)",
                severity="medium",
                source="token_movement_strategy",
                timestamp=datetime.now(),
                data={
                    **result,
                    "chain_id": event.chain_id,
                    "chain_name": ChainInfo.get_chain_name(event.chain_id),
                    "from_address": event.from_address,
                    "transaction_hash": event.transaction_hash,
                    "block_number": event.block_number
                }
            ))
        
        return alerts
