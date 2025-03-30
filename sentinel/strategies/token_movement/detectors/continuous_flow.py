"""
Continuous fund flow detector for the Token Movement Strategy.
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
from sentinel.core.events import TokenTransferEvent
from sentinel.core.alerts import Alert
from sentinel.strategies.token_movement.detectors.base import BaseDetector
from sentinel.strategies.token_movement.utils.chain_info import ChainInfo
from sentinel.logger import logger

class ContinuousFlowDetector(BaseDetector):
    """
    Detector for continuous fund inflow or outflow patterns.
    
    This detector identifies addresses that show a consistent pattern of funds
    either flowing in or out, which may indicate accumulation, distribution,
    or other significant trading patterns.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the continuous flow detector.
        
        Args:
            config: Configuration parameters for the detector
        """
        super().__init__(config)
        self.min_transactions = self.config.get('min_transactions', 5)
        self.flow_ratio_threshold = self.config.get('flow_ratio_threshold', 0.7)  # 70% in one direction
        self.significant_threshold = self.config.get('significant_threshold', 100.0)
        self.window_hours = self.config.get('window_hours', 24)
        
    async def detect(self, event: TokenTransferEvent, context: Dict[str, Any]) -> List[Alert]:
        """
        Detect continuous fund flow patterns and generate alerts.
        
        Args:
            event: The token transfer event to analyze
            context: Additional context information
            
        Returns:
            List[Alert]: List of alerts generated, if any
        """
        alerts = []
        chain_id = event.chain_id
        address = event.from_address
        
        # Get transfers by address from context
        transfers_by_address = context.get('transfers_by_address', {})
        address_key = (chain_id, address)
        
        # Get recent transfers for this address
        address_transfers = transfers_by_address.get(address_key, [])
        
        # Skip if we don't have enough data
        if len(address_transfers) < self.min_transactions:
            return []
            
        # Calculate inflow and outflow
        total_inflow = 0.0
        total_outflow = 0.0
        inflow_count = 0
        outflow_count = 0
        
        # Track tokens involved
        token_symbols = set()
        
        for transfer in address_transfers:
            # Skip transfers that are too old
            if (event.block_timestamp - transfer.block_timestamp).total_seconds() > (self.window_hours * 3600):
                continue
                
            if transfer.to_address.lower() == address.lower():
                # This is an inflow
                total_inflow += transfer.formatted_value
                inflow_count += 1
            elif transfer.from_address.lower() == address.lower():
                # This is an outflow
                total_outflow += transfer.formatted_value
                outflow_count += 1
                
            # Track token symbols
            if transfer.token_symbol:
                token_symbols.add(transfer.token_symbol)
        
        # Calculate net flow
        net_flow = total_inflow - total_outflow
        total_volume = total_inflow + total_outflow
        
        # Skip if total volume is too small
        if total_volume < self.significant_threshold:
            return []
            
        # Calculate flow ratio (-1.0 to 1.0, where -1.0 is all outflow, 1.0 is all inflow)
        flow_ratio = net_flow / total_volume if total_volume > 0 else 0
        
        # Determine if this is a significant flow pattern
        if abs(flow_ratio) >= self.flow_ratio_threshold:
            is_inflow = flow_ratio > 0
            flow_type = "Inflow" if is_inflow else "Outflow"
            
            # Determine pattern type
            if inflow_count + outflow_count >= 10:
                pattern_type = 'long_term_biased'
            else:
                pattern_type = 'short_term_consecutive'
                
            # Adjust alert severity based on amount
            if abs(net_flow) > self.significant_threshold * 10:
                severity = "high"
            elif abs(net_flow) > self.significant_threshold:
                severity = "medium"
            else:
                severity = "info"
                
            # Format description based on pattern type
            if pattern_type == 'short_term_consecutive':
                recent_count = inflow_count if is_inflow else outflow_count
                recent_amount = total_inflow if is_inflow else total_outflow
                description = (f"Address {address} shows {recent_count} consecutive "
                              f"{flow_type.lower()} transactions of "
                              f"{', '.join(token_symbols) if token_symbols else 'tokens'} "
                              f"totaling {recent_amount:.2f}")
                title = f"Short-term Consecutive {flow_type} Pattern"
            else:
                transaction_count = inflow_count + outflow_count
                flow_ratio_percent = abs(flow_ratio) * 100
                description = (f"Address {address} shows consistent {flow_type.lower()} pattern "
                              f"({flow_ratio_percent:.1f}% of activity) of "
                              f"{', '.join(token_symbols) if token_symbols else 'tokens'} "
                              f"across {transaction_count} transactions, "
                              f"net {flow_type.lower()}: {abs(net_flow):.2f}")
                title = f"Consistent {flow_type} Pattern Detected"
                
            result = {
                'address': address,
                'flow_type': flow_type,
                'pattern_type': pattern_type,
                'flow_ratio': flow_ratio,
                'total_inflow': total_inflow,
                'total_outflow': total_outflow,
                'net_flow': net_flow,
                'inflow_count': inflow_count,
                'outflow_count': outflow_count,
                'window_hours': self.window_hours,
                'token_symbols': list(token_symbols)
            }
            
            logger.info(f"Continuous {flow_type.lower()} detected for address {address}: pattern={pattern_type}, net_flow={abs(net_flow)}")
            
            alerts.append(Alert(
                title=title,
                description=description,
                severity=severity,
                source="token_movement_strategy",
                timestamp=datetime.now(),
                data={
                    **result,
                    "chain_id": event.chain_id,
                    "chain_name": ChainInfo.get_chain_name(event.chain_id),
                    "transaction_hash": event.transaction_hash,
                    "block_number": event.block_number
                }
            ))
            
        return alerts
