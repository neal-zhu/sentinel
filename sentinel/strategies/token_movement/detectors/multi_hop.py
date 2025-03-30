"""
Multi-hop pattern detector for the Token Movement Strategy.
"""
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime, timedelta
from sentinel.core.events import TokenTransferEvent
from sentinel.core.alerts import Alert
from sentinel.strategies.token_movement.detectors.base import BaseDetector
from sentinel.strategies.token_movement.utils.chain_info import ChainInfo
from sentinel.logger import logger

class MultiHopDetector(BaseDetector):
    """
    Detector for multi-hop transfer patterns common in arbitrage.
    
    This detector identifies patterns where tokens move through multiple addresses
    in a short time window, which is a common pattern in arbitrage transactions.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the multi-hop pattern detector.
        
        Args:
            config: Configuration parameters for the detector
        """
        super().__init__(config)
        self.arbitrage_time_window = self.config.get('arbitrage_time_window', 60)  # seconds
        self.min_addresses = self.config.get('min_addresses', 3)
        self.min_tokens = self.config.get('min_tokens', 2)
        
    async def detect(self, event: TokenTransferEvent, context: Dict[str, Any]) -> List[Alert]:
        """
        Detect multi-hop transfer patterns and generate alerts.
        
        Args:
            event: The token transfer event to analyze
            context: Additional context information
            
        Returns:
            List[Alert]: List of alerts generated, if any
        """
        alerts = []
        
        # Skip if this is not a contract interaction
        if not event.has_contract_interaction:
            return []
            
        # Get transfers by address from context
        transfers_by_address = context.get('transfers_by_address', {})
        
        # Get chain ID and block timestamp
        chain_id = event.chain_id
        block_timestamp = event.block_timestamp
        
        # Look for related transfers in a short time window
        # For arbitrage, transfers typically happen in the same block or transaction
        window_start = block_timestamp - timedelta(seconds=self.arbitrage_time_window)
        
        # Get recent transfers for both addresses
        from_key = (chain_id, event.from_address)
        to_key = (chain_id, event.to_address)
        
        from_transfers = [t for t in transfers_by_address.get(from_key, []) 
                         if t.block_timestamp >= window_start]
        to_transfers = [t for t in transfers_by_address.get(to_key, []) 
                       if t.block_timestamp >= window_start]
        
        # Combine and sort by timestamp
        all_transfers = from_transfers + to_transfers
        all_transfers.sort(key=lambda t: t.block_timestamp)
        
        # If we don't have enough transfers, not a multi-hop pattern
        if len(all_transfers) < 3:  # Need at least 3 transfers for a multi-hop
            return []
            
        # Check for circular pattern (A->B->C->A)
        addresses_involved = set()
        for t in all_transfers:
            addresses_involved.add(t.from_address.lower())
            addresses_involved.add(t.to_address.lower())
            
        # Check if we have a potential arbitrage pattern
        # 1. Multiple addresses involved (at least 3)
        # 2. Circular pattern (some address appears as both sender and receiver)
        # 3. Different tokens involved
        
        if len(addresses_involved) >= self.min_addresses:
            # Check for circular pattern
            has_circular = False
            for addr in addresses_involved:
                # Count how many times this address appears as sender and receiver
                as_sender = sum(1 for t in all_transfers if t.from_address.lower() == addr)
                as_receiver = sum(1 for t in all_transfers if t.to_address.lower() == addr)
                
                if as_sender > 0 and as_receiver > 0:
                    has_circular = True
                    break
                    
            if has_circular:
                # Check for different tokens
                tokens_involved = set(t.token_address for t in all_transfers)
                if len(tokens_involved) >= self.min_tokens:  # At least 2 different tokens
                    # This looks like an arbitrage pattern
                    pattern_data = {
                        'pattern_type': 'multi_hop',
                        'addresses_involved': list(addresses_involved),
                        'tokens_involved': list(tokens_involved),
                        'transfer_count': len(all_transfers),
                        'time_window_seconds': self.arbitrage_time_window,
                        'transaction_hash': event.transaction_hash,
                        'block_number': event.block_number
                    }
                    
                    logger.info(f"Multi-hop transfer pattern detected: {len(addresses_involved)} addresses, {len(tokens_involved)} tokens")
                    
                    alerts.append(Alert(
                        title="Potential Arbitrage Pattern Detected",
                        description=f"Multi-hop transfer pattern involving {len(addresses_involved)} addresses and {len(tokens_involved)} tokens",
                        severity="medium",
                        source="token_movement_strategy",
                        timestamp=datetime.now(),
                        data={
                            **pattern_data,
                            "chain_id": event.chain_id,
                            "chain_name": ChainInfo.get_chain_name(event.chain_id),
                            "transaction_hash": event.transaction_hash,
                            "block_number": event.block_number
                        }
                    ))
        
        return alerts
