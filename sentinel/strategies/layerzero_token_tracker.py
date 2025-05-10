"""
LayerZero Token Tracker Strategy

This strategy processes events from LayerZero endpoint contracts to detect and track new cross-chain tokens.
It specifically looks for DelegateSet events, where the sender parameter is the token contract address.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from web3 import Web3

from sentinel.core.actions import Action
from sentinel.core.base import Strategy
from sentinel.core.events import Event
from sentinel.core.token_storage import TokenStorage, create_token_storage
from sentinel.logger import logger


class CrossChainTokenAction(Action):
    """Action for new cross-chain token detection"""

    action_type = "new_cross_chain_token"
    
    def __init__(
        self,
        chain_id: int,
        endpoint_address: str,
        token_address: str,  # This is the sender address in DelegateSet
        delegate_address: str,
        transaction_hash: str,
        block_number: int,
        block_timestamp: datetime,
        detection_time: datetime,
    ):
        super().__init__(
            type=self.action_type,
            data={
                "chain_id": chain_id,
                "endpoint_address": endpoint_address,
                "token_address": token_address,
                "delegate_address": delegate_address,
                "transaction_hash": transaction_hash,
                "block_number": block_number,
                "block_timestamp": block_timestamp.isoformat() if isinstance(block_timestamp, datetime) else block_timestamp,
                "detection_time": detection_time.isoformat() if isinstance(detection_time, datetime) else detection_time,
            }
        )
        self.chain_id = chain_id
        self.endpoint_address = endpoint_address
        self.token_address = token_address
        self.delegate_address = delegate_address
        self.transaction_hash = transaction_hash
        self.block_number = block_number
        self.block_timestamp = block_timestamp
        self.detection_time = detection_time

    def as_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "chain_id": self.chain_id,
            "endpoint_address": self.endpoint_address,
            "token_address": self.token_address,
            "delegate_address": self.delegate_address,
            "transaction_hash": self.transaction_hash,
            "block_number": self.block_number,
            "block_timestamp": self.block_timestamp.isoformat() if isinstance(self.block_timestamp, datetime) else self.block_timestamp,
            "detection_time": self.detection_time.isoformat() if isinstance(self.detection_time, datetime) else self.detection_time,
        }

    def __str__(self) -> str:
        return (
            f"New Cross-Chain Token Detected:\n"
            f"  Chain ID: {self.chain_id}\n"
            f"  Endpoint: {self.endpoint_address}\n"
            f"  Token: {self.token_address}\n"
            f"  Delegate: {self.delegate_address}\n"
            f"  Transaction: {self.transaction_hash}\n"
            f"  Block: {self.block_number}\n"
            f"  Block Time: {self.block_timestamp}\n"
            f"  Detection Time: {self.detection_time}\n"
        )


class LayerZeroTokenTrackerStrategy(Strategy):
    """
    Strategy to track new cross-chain tokens through LayerZero DelegateSet events
    
    The strategy monitors events from LayerZero endpoint contracts to discover
    new cross-chain token configurations. It parses raw events to extract the
    sender address (the token contract address) from DelegateSet events.
    """

    __component_name__ = "layerzero_token_tracker"
    
    # DelegateSet event signature
    DELEGATE_SET_EVENT = "DelegateSet(address,address)"
    DELEGATE_SET_SIGNATURE = Web3.keccak(text=DELEGATE_SET_EVENT).hex()

    def __init__(
        self,
        # Storage configuration
        storage_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize LayerZero Token Tracker Strategy
        
        Args:
            storage_config: Configuration for token storage
                Example: {"type": "sqlite", "db_path": "data/tokens.db"}
                Default: {"type": "json", "file_path": "data/layerzero_tokens.json"}
        """
        super().__init__()
        
        # Set up token storage
        if storage_config is None:
            storage_config = {
                "type": "json", 
                "file_path": "data/layerzero_tokens.json"
            }
            
        self.token_storage = create_token_storage(storage_config)
        logger.info(f"Initialized LayerZero token tracker with {storage_config['type']} storage")

    def _is_delegate_set_event(self, event: Event) -> bool:
        """
        Check if an event is a DelegateSet event
        
        Args:
            event: The event to check
            
        Returns:
            bool: True if the event is a DelegateSet event
        """
        # Get event data
        event_data = getattr(event, "data", {})
        
        # If event is from our collector, it will have a log field with topics
        log = event_data.get("log", {})
        topics = log.get("topics", [])
        
        # Check if first topic matches DelegateSet signature
        if topics and topics[0].hex() == self.DELEGATE_SET_SIGNATURE:
            return True
            
        return False
    
    def _parse_delegate_set_event(self, event: Event) -> Optional[Dict[str, Any]]:
        """
        Parse a DelegateSet event to extract token address and other information
        
        Args:
            event: The event to parse
            
        Returns:
            Optional[Dict[str, Any]]: Parsed event data or None if parsing failed
        """
        try:
            # Get event data
            event_data = getattr(event, "data", {})
            
            # Extract chain ID
            chain_id = event_data.get("chain_id")
            if not chain_id:
                logger.warning("Event missing chain_id")
                return None
                
            # Get log data
            log = event_data.get("log", {})
            if not log:
                logger.warning("Event missing log data")
                return None
                
            # Extract topics
            topics = log.get("topics", [])
            if len(topics) < 3:  # Need at least 3 topics for a DelegateSet event
                logger.warning(f"Not enough topics in event: {len(topics)}")
                return None
                
            # Topics[0] is the event signature
            # Topics[1] is the indexed 'sender' address (token contract)
            # Topics[2] is the indexed 'delegate' address
            token_address = Web3.to_checksum_address("0x" + topics[1].hex()[-40:])
            delegate_address = Web3.to_checksum_address("0x" + topics[2].hex()[-40:])
            
            # Extract other information
            tx = event_data.get("tx", {})
            block = event_data.get("block", {})
            
            endpoint_address = log.get("address")
            transaction_hash = log.get("transactionHash", b"").hex()
            block_number = log.get("blockNumber")
            
            # Get timestamp from block or event
            block_timestamp = block.get("timestamp")
            if block_timestamp:
                if isinstance(block_timestamp, (int, float)):
                    block_timestamp = datetime.fromtimestamp(block_timestamp)
                elif isinstance(block_timestamp, str):
                    # Try to parse ISO format timestamp
                    try:
                        block_timestamp = datetime.fromisoformat(block_timestamp)
                    except ValueError:
                        pass
            
            # If no timestamp found, use current time
            if not block_timestamp:
                block_timestamp = datetime.now()
                
            return {
                "chain_id": chain_id,
                "endpoint_address": endpoint_address,
                "token_address": token_address,
                "delegate_address": delegate_address,
                "transaction_hash": transaction_hash,
                "block_number": block_number,
                "block_timestamp": block_timestamp,
            }
        except Exception as e:
            logger.error(f"Error parsing DelegateSet event: {e}")
            return None

    async def process_event(self, event: Event) -> List[Action]:
        """
        Process Web3 events and identify LayerZero DelegateSet events to track new cross-chain tokens
        
        Args:
            event: Event to process (generic Web3 event)
            
        Returns:
            List[Action]: List of actions
        """
        actions = []
        
        # Check if this is a DelegateSet event
        if not self._is_delegate_set_event(event):
            return []
            
        # Parse the DelegateSet event
        event_data = self._parse_delegate_set_event(event)
        if not event_data:
            logger.warning("Failed to parse DelegateSet event")
            return []
            
        # Extract token information
        chain_id = event_data["chain_id"]
        token_address = event_data["token_address"]
        
        # Only process new tokens
        if not self.token_storage.contains_token(chain_id, token_address):
            # Create action for the new cross-chain token
            action = CrossChainTokenAction(
                chain_id=chain_id,
                endpoint_address=event_data["endpoint_address"],
                token_address=token_address,
                delegate_address=event_data["delegate_address"],
                transaction_hash=event_data["transaction_hash"],
                block_number=event_data["block_number"],
                block_timestamp=event_data["block_timestamp"],
                detection_time=datetime.now(),
            )
            
            actions.append(action)
            
            # Store token metadata
            metadata = {
                "endpoint_address": event_data["endpoint_address"],
                "first_delegate": event_data["delegate_address"],
                "first_transaction": event_data["transaction_hash"],
                "first_block": event_data["block_number"],
                "detection_time": datetime.now().isoformat()
            }
            
            # Add to token storage
            if self.token_storage.add_token(chain_id, token_address, metadata):
                logger.info(f"New cross-chain token detected: {token_address} (Chain ID: {chain_id})")
            else:
                logger.warning(f"Failed to add token to storage: {token_address} (Chain ID: {chain_id})")
        
        return actions
        
    async def _stop(self):
        """Clean up resources when the strategy is stopped"""
        try:
            self.token_storage.close()
            logger.info("Closed token storage connection")
        except Exception as e:
            logger.error(f"Error closing token storage: {e}") 