from web3.types import BlockData, TxData


from datetime import datetime


class Event:
    type: str

class TransactionEvent(Event):
    """交易事件"""
    def __init__(self, transaction: TxData, block: BlockData):
        self.type = "transaction"
        self.transaction = transaction
        self.block = block
        self.timestamp = datetime.fromtimestamp(block.timestamp)

    def __str__(self) -> str:
        return (
            f"Transaction: {self.transaction.hash.hex()}\n"
            f"Block: {self.block.number}\n"
            f"From: {self.transaction['from']}\n"
            f"To: {self.transaction['to']}\n"
            f"Value: {self.transaction['value']}\n"
            f"Timestamp: {self.timestamp}"
        )
