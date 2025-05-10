"""
LayerZero Event Utilities

Utility functions for processing LayerZero events.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from web3 import Web3

from sentinel.core.events import LayerZeroDelegateEvent, Event
from sentinel.logger import logger


def process_layerzero_delegate_event(context: Dict[str, Any]) -> Optional[Event]:
    """
    Process a LayerZero DelegateSet event
    
    In LayerZero's DelegateSet event, the 'sender' parameter is the token contract address
    that is being configured for cross-chain transfers. The 'delegate' parameter is the 
    address authorized to send messages on behalf of the token contract.
    
    Args:
        context: Context dictionary containing log, tx, block and chain data
        
    Returns:
        LayerZeroDelegateEvent: Event object or None if processing failed
    """
    try:
        # Extract data from context
        chain_id = context["chain_id"]
        log = context["log"]
        tx = context["tx"]
        block_timestamp = context["block_timestamp"]
        
        # Get endpoint address (contract address that emitted the event)
        endpoint_address = log["address"]
        
        # Extract data from log
        topics = log["topics"]
        
        # Extract sender and delegate addresses from topics
        # Topics[0] is the event signature
        # Topics[1] is the indexed 'sender' address (the token contract address)
        # Topics[2] is the indexed 'delegate' address (authorized to send on behalf of token)
        sender_address = Web3.to_checksum_address(
            "0x" + topics[1].hex()[-40:]
        )
        delegate_address = Web3.to_checksum_address(
            "0x" + topics[2].hex()[-40:]
        )
        
        # Get transaction information
        tx_hash = log["transactionHash"].hex()
        from_address = tx.get("from", "0x0000000000000000000000000000000000000000")
        
        # Create delegate event
        delegate_event = LayerZeroDelegateEvent(
            chain_id=chain_id,
            endpoint_address=endpoint_address,
            from_address=from_address,
            sender_address=sender_address,  # This is the token contract address
            delegate_address=delegate_address,
            transaction_hash=tx_hash,
            block_number=log["blockNumber"],
            block_timestamp=block_timestamp,
            log_index=log["logIndex"],
        )
        
        return delegate_event
    except Exception as e:
        logger.error(f"Error processing LayerZero delegate event: {e}")
        return None 