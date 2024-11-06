from typing import List, Optional, Callable, Any, AsyncGenerator
from web3 import AsyncWeb3, AsyncHTTPProvider
from web3.types import BlockData, TxData
import asyncio
from datetime import datetime

from ..core.base import Collector
from ..core.events import Event
from ..logger import logger

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

class TransactionCollector(Collector):
    __component_name__ = "web3_transaction"
    
    def __init__(
        self,
        rpc_url: Optional[str] = None,
        start_block: Optional[int] = None,
        block_time: int = 12,
        max_blocks_per_batch: int = 100
    ):
        """
        初始化交易收集器

        Args:
            rpc_url: RPC节点URL，如果不提供则从配置中读取
            start_block: 开始区块，如果不提供则从最新区块开始
            block_time: 预期的出块时间（秒）
            max_blocks_per_batch: 每批处理的最大区块数
        """
        super().__init__()
        self.w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        self.start_block = start_block
        self.block_time = block_time
        self.max_blocks_per_batch = max_blocks_per_batch
        self.last_processed_block = None
        self._running = False

    async def events(self) -> AsyncGenerator[TransactionEvent, None]:
        """
        生成交易事件流

        Yields:
            TransactionEvent: 交易事件
        """
        
        # 如果没有指定起始区块，使用最新区块
        if self.start_block is None:
            self.start_block = await self.get_latest_block_number()
        
        self.last_processed_block = self.start_block - 1
        logger.info(f"Starting transaction collector from block {self.start_block}")
        
        while self._running:
            try:
                async for event in self._process_new_blocks():
                    yield event
                # 等待预计的出块时间
                await asyncio.sleep(self.block_time)
            except Exception as e:
                logger.error(f"Error processing blocks: {str(e)}")
                await asyncio.sleep(self.block_time)


    async def get_latest_block_number(self) -> int:
        """获取最新区块号"""
        return await self.w3.eth.block_number

    async def _process_new_blocks(self) -> AsyncGenerator[TransactionEvent, None]:
        """处理新区块"""
        latest_block = await self.get_latest_block_number()
        
        if latest_block <= self.last_processed_block:
            return
        
        start_block = self.last_processed_block + 1
        end_block = min(
            latest_block,
            start_block + self.max_blocks_per_batch - 1
        )
        
        logger.info(f"Processing blocks {start_block} to {end_block}")
        
        for block_num in range(start_block, end_block + 1):
            async for event in self._process_block_number(block_num):
                yield event
        
        self.last_processed_block = end_block

    async def _process_block_number(self, block_number: int) -> AsyncGenerator[TransactionEvent, None]:
        """处理指定区块号的区块"""
        block = await self.get_block(block_number)
        if block:
            async for event in self._process_block(block):
                yield event

    async def get_block(self, block_number: int) -> Optional[BlockData]:
        """获取区块数据"""
        try:
            return await self.w3.eth.get_block(block_number, full_transactions=True)
        except Exception as e:
            logger.error(f"Error getting block {block_number}: {str(e)}")
            return None

    async def _process_block(self, block: BlockData) -> AsyncGenerator[TransactionEvent, None]:
        """处理单个区块"""
        timestamp = datetime.fromtimestamp(block.timestamp)
        logger.info(f"Processing block {block.number} ({timestamp})")
        
        for tx in block.transactions:
            yield TransactionEvent(transaction=tx, block=block)

    async def get_transaction_receipt(self, tx_hash: str):
        """获取交易收据"""
        try:
            return await self.w3.eth.get_transaction_receipt(tx_hash)
        except Exception as e:
            logger.error(f"Error getting receipt for tx {tx_hash}: {str(e)}")
            return None

    async def wait_for_transaction(self, tx_hash: str, timeout: int = 120):
        """等待交易确认"""
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                receipt = await self.get_transaction_receipt(tx_hash)
                if receipt:
                    return receipt
            except Exception:
                pass
            await asyncio.sleep(1)
        raise TimeoutError(f"Transaction {tx_hash} not confirmed within {timeout} seconds")

    async def get_transaction_count(self, address: str, block_identifier: str = 'latest'):
        """获取地址的交易数量（nonce）"""
        return await self.w3.eth.get_transaction_count(address, block_identifier)

    async def estimate_gas(self, transaction: dict):
        """估算交易的gas消耗"""
        try:
            return await self.w3.eth.estimate_gas(transaction)
        except Exception as e:
            logger.error(f"Error estimating gas: {str(e)}")
            return None
