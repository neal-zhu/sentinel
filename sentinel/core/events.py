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