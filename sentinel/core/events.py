from datetime import datetime
from typing import Optional, Dict, Any
from web3.types import BlockData, TxData
from pydantic import BaseModel, Field

class Event(BaseModel):
    """事件基类"""
    type: str = Field(...)  # 必须提供类型

    class Config:
        """Pydantic配置"""
        frozen = True  # 使Event实例不可变
        arbitrary_types_allowed = True  # 允许任意类型

class TransactionEvent(Event):
    """交易事件"""
    type: str = "transaction"  # 默认类型
    transaction: Dict[str, Any]  # 使用字典存储交易数据
    block: Dict[str, Any]  # 使用字典存储区块数据
    timestamp: datetime
    
    @property
    def tx_data(self) -> TxData:
        """获取原始交易数据"""
        return TxData(self.transaction)
    
    @property
    def block_data(self) -> BlockData:
        """获取原始区块数据"""
        return BlockData(self.block)
    
    def __str__(self) -> str:
        """格式化事件内容为字符串"""
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
        """转换为字典格式"""
        return {
            "type": self.type,
            "transaction_hash": self.transaction['hash'].hex(),
            "block_number": self.block['number'],
            "from": self.transaction['from'],
            "to": self.transaction.get('to', 'Contract Creation'),
            "value": self.transaction['value'],
            "timestamp": self.timestamp.isoformat()
        }