from typing import Optional, AsyncGenerator
from web3 import AsyncWeb3, AsyncHTTPProvider
from web3.types import BlockData
import asyncio
from datetime import datetime

from ..core.events import TransactionEvent
from ..core.base import Collector
from ..logger import logger

class TransactionCollector(Collector):
    __component_name__ = "web3_transaction"
    
    def __init__(
        self,
        rpc_url: str,
        start_block: Optional[int] = None,
        block_time: int = 12,
        max_blocks_per_batch: int = 100,
        retry_interval: int = 5,
        max_retries: int = 3
    ):
        """
        初始化交易收集器

        Args:
            rpc_url: RPC节点URL
            start_block: 开始区块，如果不提供则从最新区块开始
            block_time: 预期的出块时间（秒）
            max_blocks_per_batch: 每批处理的最大区块数
            retry_interval: 重试间隔（秒）
            max_retries: 最大重试次数
        """
        super().__init__()
        if not rpc_url:
            raise ValueError("RPC URL is required")
            
        self.w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        self.start_block = start_block
        self.block_time = block_time
        self.max_blocks_per_batch = max_blocks_per_batch
        self.retry_interval = retry_interval
        self.max_retries = max_retries
        self.last_processed_block = None

    async def _start(self):
        """启动收集器时的初始化"""
        if self.start_block is None:
            self.start_block = await self._get_latest_block_with_retry()
            logger.info(f"Starting from latest block: {self.start_block}")
        
        self.last_processed_block = self.start_block - 1
        logger.info(f"Initialized TransactionCollector at block {self.last_processed_block}")

    async def events(self) -> AsyncGenerator[TransactionEvent, None]:
        """生成交易事件流"""
        while self._running:
            try:
                async for event in self._process_new_blocks():
                    yield event
                # 等待预计的出块时间
                await asyncio.sleep(self.block_time)
            except Exception as e:
                logger.error(f"Error in events stream: {str(e)}")
                await asyncio.sleep(self.retry_interval)

    async def _get_latest_block_with_retry(self) -> int:
        """带重试机制的获取最新区块号"""
        for attempt in range(self.max_retries):
            try:
                return await self.w3.eth.block_number
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                logger.warning(f"Failed to get latest block number (attempt {attempt + 1}): {e}")
                await asyncio.sleep(self.retry_interval)

    async def _process_new_blocks(self) -> AsyncGenerator[TransactionEvent, None]:
        """处理新区块"""
        latest_block = await self._get_latest_block_with_retry()
        
        if latest_block <= self.last_processed_block:
            return
        
        start_block = self.last_processed_block + 1
        end_block = min(
            latest_block,
            start_block + self.max_blocks_per_batch - 1
        )
        
        logger.debug(f"Processing blocks {start_block} to {end_block}")
        
        for block_num in range(start_block, end_block + 1):
            block = await self._get_block_with_retry(block_num)
            if block:
                async for event in self._process_block(block):
                    yield event
            else:
                logger.warning(f"Skipping block {block_num} due to retrieval failure")
        
        self.last_processed_block = end_block

    async def _get_block_with_retry(self, block_number: int) -> Optional[BlockData]:
        """带重试机制的获取区块数据"""
        for attempt in range(self.max_retries):
            try:
                return await self.w3.eth.get_block(block_number, full_transactions=True)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"Failed to get block {block_number} after {self.max_retries} attempts: {e}")
                    return None
                logger.warning(f"Failed to get block {block_number} (attempt {attempt + 1}): {e}")
                await asyncio.sleep(self.retry_interval)

    async def _process_block(self, block: BlockData) -> AsyncGenerator[TransactionEvent, None]:
        """处理单个区块"""
        timestamp = datetime.fromtimestamp(block.timestamp)
        logger.debug(f"Processing block {block.number} ({timestamp})")
        
        for tx in block.transactions:
            yield TransactionEvent(transaction=tx, block=block, timestamp=timestamp)
