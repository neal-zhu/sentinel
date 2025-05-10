"""
Web3 Event Collector

A generic collector for monitoring smart contract events on EVM-compatible blockchains.
Supports filtering by event signatures and custom topics.
"""

import asyncio
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple, Union

from web3 import AsyncWeb3, Web3
from web3.types import EventData, FilterParams, LogReceipt

from sentinel.core.base import Collector
from sentinel.core.events import Event, Web3Event
from sentinel.core.web3.multi_provider import AsyncMultiNodeProvider
from sentinel.logger import logger


class Web3EventCollector(Collector):
    """
    Generic Web3 Event Collector

    A flexible collector for monitoring blockchain events with customizable 
    filtering and event processing capabilities.
    """

    __component_name__ = "web3_event"

    def __init__(
        self,
        # Chain identification
        chain_id: int,
        # Network configuration
        rpc_endpoints: List[str],
        # Event filtering
        contract_address: str,  # Single contract address to monitor
        event_signatures: Optional[List[str]] = None,  # Event signatures to filter
        # Monitoring settings
        polling_interval: int = 15,  # Polling interval in seconds
        max_blocks_per_scan: int = 100,  # Maximum blocks to scan per iteration
        start_block: Optional[int] = None,  # Starting block number
    ):
        """
        Initialize Web3 Event Collector

        Args:
            chain_id: ID of the blockchain to monitor
            rpc_endpoints: List of RPC endpoints for the blockchain
            contract_address: Contract address to monitor
            event_signatures: List of event signatures to filter (e.g., ["Transfer(address,address,uint256)"])
            polling_interval: Polling interval in seconds
            max_blocks_per_scan: Maximum blocks to scan per polling cycle
            start_block: Starting block number
        """
        super().__init__()

        if not rpc_endpoints:
            raise ValueError("At least one RPC endpoint must be provided")
        
        if not contract_address:
            raise ValueError("Contract address must be provided")

        # Initialize parameters
        self.chain_id = chain_id
        self.polling_interval = polling_interval
        self.max_blocks_per_scan = max_blocks_per_scan
        self.start_block = start_block or 0
        
        # Clean and normalize address
        self.contract_address = contract_address.lower()
        
        # Event filtering
        self.event_signatures = event_signatures or []
                
        # Web3 setup
        provider = AsyncMultiNodeProvider(endpoint_uri=rpc_endpoints)
        self.web3 = AsyncWeb3(provider)
        
        # Generate event signature hashes
        self.event_signature_hashes = []
        for sig in self.event_signatures:
            self.event_signature_hashes.append(self.web3.keccak(text=sig).hex())
            
        # Last checked block (in-memory cache)
        self.last_checked_block = 0

    async def _initialize_last_blocks(self):
        """Initialize last processed block for the chain"""
        try:
            if self.start_block > 0:
                logger.info(
                    f"Starting from configured block {self.start_block} for chain {self.chain_id}"
                )
                self.last_checked_block = self.start_block
            else:
                # Default to current block
                try:
                    current_block = await self.web3.eth.block_number
                    logger.info(
                        f"Starting from current block {current_block} for chain {self.chain_id}"
                    )
                    self.last_checked_block = current_block
                except Exception as e:
                    logger.error(
                        f"Unable to get current block for chain {self.chain_id}: {e}"
                    )
                    self.last_checked_block = 0
        except Exception as e:
            logger.error(
                f"Error initializing last blocks for chain {self.chain_id}: {e}"
            )
            self.last_checked_block = 0

    async def _start(self):
        """Collector initialization logic on startup"""
        # Initialize last blocks
        await self._initialize_last_blocks()

        # Verify Web3 connection
        try:
            if not await self.web3.is_connected():
                logger.warning(
                    f"Unable to connect to network with chain ID {self.chain_id}"
                )
        except Exception as e:
            logger.error(
                f"Error checking connection to network with chain ID {self.chain_id}: {e}"
            )

    async def _stop(self):
        """Collector cleanup logic on shutdown"""
        pass

    def _build_filter_params(self, from_block: int, to_block: int) -> FilterParams:
        """
        Build event filter parameters

        Args:
            from_block: Starting block
            to_block: Ending block

        Returns:
            FilterParams: Filter parameters for get_logs
        """
        # Basic filter with block range and contract address
        filter_params: Dict[str, Any] = {
            "fromBlock": from_block,
            "toBlock": to_block,
            "address": self.web3.to_checksum_address(self.contract_address),
        }
        
        # Add event signature hash filters
        if self.event_signature_hashes:
            filter_params["topics"] = [self.event_signature_hashes]
            
        return filter_params

    async def _get_log_data(self, log: LogReceipt) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Get additional transaction and block data for a log

        Args:
            log: The log receipt

        Returns:
            Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]: Transaction data and block data
        """
        tx = None
        block = None
        
        try:
            # Get transaction data
            tx_obj = await self.web3.eth.get_transaction(log["transactionHash"])
            if tx_obj:
                tx = dict(tx_obj)
            
            # Get block data for timestamp
            block_obj = await self.web3.eth.get_block(log["blockNumber"])
            if block_obj:
                block = dict(block_obj)
        except Exception as e:
            logger.error(f"Error getting transaction or block data: {e}")
            
        return tx, block

    async def _scan_events(
        self, from_block: int, to_block: int
    ) -> AsyncGenerator[Event, None]:
        """
        Scan a block range for events

        Args:
            from_block: Starting block
            to_block: Ending block

        Yields:
            Event: Processed events
        """
        try:
            # Build filter parameters
            filter_params = self._build_filter_params(from_block, to_block)
            
            # Get logs matching the filter
            logs = await self.web3.eth.get_logs(filter_params)
            
            # Process each log
            for log in logs:
                yield Web3Event(
                    type="web3_event",
                    event=log,
                )
        except Exception as e:
            logger.error(
                f"Error getting logs for chain {self.chain_id} from blocks {from_block}-{to_block}: {e}"
            )

    async def events(self) -> AsyncGenerator[Event, None]:
        """
        Generate event stream

        Polls the blockchain periodically to check for new events.

        Yields:
            Event: Processed events
        """
        if not self._running:
            await self.start()

        while self._running:
            try:  # Add an outer try/except to make the generator more robust
                try:
                    # Get current block
                    current_block = await self.web3.eth.block_number
                    last_checked = self.last_checked_block

                    # Ensure we only scan new blocks
                    if current_block <= last_checked:
                        # No new blocks, wait for next polling cycle
                        await asyncio.sleep(self.polling_interval)
                        continue

                    # Limit blocks per scan
                    from_block = last_checked + 1
                    to_block = min(
                        current_block, from_block + self.max_blocks_per_scan - 1
                    )

                    logger.info(
                        f"Scanning chain {self.chain_id} blocks {from_block}-{to_block} for contract {self.contract_address}"
                    )

                    # Track statistics for reporting
                    event_count = 0

                    # Scan and yield events immediately
                    async for event in self._scan_events(from_block, to_block):
                        event_count += 1
                        yield event

                    # Update last checked block in memory
                    self.last_checked_block = to_block

                    # Log statistics
                    logger.info(
                        f"Processed blocks {from_block}-{to_block}, found {event_count} events on chain {self.chain_id}"
                    )

                except Exception as e:
                    logger.error(
                        f"Error collecting events for chain {self.chain_id}: {e}"
                    )

                # Add a small yield before sleeping to make tests more reliable
                if not await self.web3.is_connected():
                    # If connection is not available, yield control briefly to avoid CPU spinning
                    await asyncio.sleep(0.01)

                # Wait for next polling cycle
                await asyncio.sleep(self.polling_interval)
            except Exception as e:
                logger.error(f"Unexpected error in events generator: {e}")
                # Brief pause to avoid tight error loops
                await asyncio.sleep(1) 