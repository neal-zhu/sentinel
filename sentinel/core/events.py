from datetime import datetime
from typing import Optional, Dict, Any
from web3.types import BlockData, TxData
from pydantic import BaseModel, Field

class Event(BaseModel):
    """Base class for all events"""
    type: str = Field(...)  # Required field

    class Config:
        """Pydantic configuration"""
        frozen = True  # Make Event instances immutable
        arbitrary_types_allowed = True  # Allow Web3 types

class TransactionEvent(Event):
    """
    Event class for blockchain transactions
    
    Stores transaction and block data in dictionary format for flexibility,
    while providing typed access through properties.
    """
    type: str = "transaction"  # Default event type
    transaction: Dict[str, Any]  # Raw transaction data
    block: Dict[str, Any]  # Raw block data
    timestamp: datetime
    
    @property
    def tx_data(self) -> TxData:
        """
        Get transaction data as Web3 TxData type
        
        Returns:
            TxData: Typed transaction data
        """
        return TxData(self.transaction)
    
    @property
    def block_data(self) -> BlockData:
        """
        Get block data as Web3 BlockData type
        
        Returns:
            BlockData: Typed block data
        """
        return BlockData(self.block)
    
    def __str__(self) -> str:
        """
        Format event content as human-readable string
        
        Returns:
            str: Formatted event information
        """
        return (
            f"Transaction Event:\n"
            f"  Hash: {self.transaction['hash'].hex()}\n"
            f"  Block: {self.block['number']}\n"
            f"  From: {self.transaction['from']}\n"
            f"  To: {self.transaction.get('to', 'Contract Creation')}\n"
            f"  Value: {self.transaction['value']}\n"
            f"  Timestamp: {self.timestamp}"
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert event to dictionary format
        
        Returns:
            Dict[str, Any]: Event data in dictionary format
        """
        return {
            "type": self.type,
            "transaction_hash": self.transaction['hash'].hex(),
            "block_number": self.block['number'],
            "from": self.transaction['from'],
            "to": self.transaction.get('to', 'Contract Creation'),
            "value": self.transaction['value'],
            "timestamp": self.timestamp.isoformat()
        }

class TokenTransferEvent(Event):
    """
    Token Transfer Event
    
    Contains detailed information about ERC20 token transfers or native token transfers
    """
    type: str = "token_transfer"  # Event type
    chain_id: int  # Chain ID
    token_address: Optional[str] = None  # Token contract address, None for ETH
    token_name: Optional[str] = None  # Token name
    token_symbol: Optional[str] = None  # Token symbol
    token_decimals: Optional[int] = None  # Token decimals
    from_address: str  # Sender address
    to_address: str  # Receiver address
    value: int  # Transfer amount (raw value)
    formatted_value: float  # Formatted transfer amount
    transaction_hash: str  # Transaction hash
    block_number: int  # Block number
    block_timestamp: datetime  # Block timestamp
    log_index: Optional[int] = None  # Log index, only valid for ERC20
    is_native: bool = False  # Whether it's a native token (ETH/BNB etc.)
    
    def __str__(self) -> str:
        """
        Format event content as human-readable string
        
        Returns:
            str: Formatted event information
        """
        token_type = "Native Token" if self.is_native else "ERC20 Token"
        token_info = f"{self.token_symbol}" if self.token_symbol else "ETH"
        
        return (
            f"Token Transfer Event:\n"
            f"  Type: {token_type}\n"
            f"  Chain: {self.chain_id}\n"
            f"  Token: {token_info}\n"
            f"  From: {self.from_address}\n"
            f"  To: {self.to_address}\n"
            f"  Value: {self.formatted_value} {token_info}\n"
            f"  TX Hash: {self.transaction_hash}\n"
            f"  Block: {self.block_number}\n"
            f"  Timestamp: {self.block_timestamp}"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert event to dictionary format
        
        Returns:
            Dict[str, Any]: Event data as dictionary
        """
        return {
            "type": self.type,
            "chain_id": self.chain_id,
            "token_address": self.token_address,
            "token_name": self.token_name,
            "token_symbol": self.token_symbol,
            "token_decimals": self.token_decimals,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "value": str(self.value),  # Convert to string to avoid large integer serialization issues
            "formatted_value": self.formatted_value,
            "transaction_hash": self.transaction_hash,
            "block_number": self.block_number,
            "block_timestamp": self.block_timestamp.isoformat(),
            "log_index": self.log_index,
            "is_native": self.is_native
        }