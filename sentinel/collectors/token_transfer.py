import asyncio
from typing import Dict, List, Optional, Any, AsyncIterable, Coroutine, TypedDict, AsyncGenerator
from datetime import datetime
from web3 import AsyncWeb3, Web3
from web3.types import FilterParams

from sentinel.core.base import Collector
from sentinel.core.events import Event, TokenTransferEvent
from sentinel.core.web3.multi_provider import AsyncMultiNodeProvider, MultiNodeProvider
from sentinel.core.web3.erc20_token import ERC20Token, AsyncERC20Token
from sentinel.core.storage import BlockchainStateStore
from sentinel.logger import logger

# Custom type helpers for Web3 types to properly handle BlockData and TxData
class SafeBlockData(TypedDict, total=False):
    """Safe wrapper for BlockData to handle optional fields"""
    timestamp: int
    transactions: List[Any]

class SafeTxData(TypedDict, total=False):
    """Safe wrapper for TxData to handle optional fields"""
    to: Optional[str]
    from_: str  # Web3.py uses from_ in Python since 'from' is reserved
    value: int
    input: str
    hash: str

# Helper function for safe timestamp conversion
def safe_timestamp_to_float(timestamp_value: Any) -> float:
    """
    Safely convert a timestamp value to float, handling various input types.
    
    Args:
        timestamp_value: The timestamp value which could be any type
        
    Returns:
        float: The timestamp as a float, or 0.0 if conversion fails
    """
    if timestamp_value is None:
        return 0.0
    
    if isinstance(timestamp_value, (int, float)):
        return float(timestamp_value)
    
    if isinstance(timestamp_value, str):
        try:
            return float(timestamp_value)
        except (ValueError, TypeError):
            pass
    
    # Try to get the timestamp as an attribute or using __int__ if available
    # Only try to access timestamp attribute on non-string objects
    try:
        if not isinstance(timestamp_value, str) and hasattr(timestamp_value, "timestamp"):
            return float(timestamp_value.timestamp())
    except (ValueError, TypeError, AttributeError):
        pass
    
    try:
        if hasattr(timestamp_value, "__int__"):
            return float(int(timestamp_value))
    except (ValueError, TypeError, AttributeError):
        pass
    
    # If all else fails, return 0
    logger.warning(f"Could not convert timestamp value: {timestamp_value} to float")
    return 0.0

# Helper function for safe list conversion
def safe_to_list(data: Any) -> List[Any]:
    """
    Safely convert data to a list, handling various input types.
    
    Args:
        data: The data to convert to a list, which could be any type
        
    Returns:
        List[Any]: The data as a list, or an empty list if conversion fails
    """
    if data is None:
        return []
    
    if isinstance(data, list):
        return data
    
    if isinstance(data, (tuple, set)):
        return list(data)
    
    # Try to convert to list if it has __iter__
    try:
        if hasattr(data, "__iter__") and not isinstance(data, (str, bytes, dict)):
            return list(data)
    except (TypeError, ValueError):
        pass
    
    # Try to access as array-like object
    try:
        if hasattr(data, "__len__") and hasattr(data, "__getitem__"):
            return [data[i] for i in range(len(data))]
    except (TypeError, ValueError, IndexError):
        pass
    
    # If all else fails, return empty list
    logger.warning(f"Could not convert data to list: {data}")
    return []

class TokenTransferCollector(Collector):
    """
    Token Transfer Collector
    
    Collects all ERC20 token transfers and native token transfers from a single blockchain.
    Focuses solely on data collection without filtering or analysis.
    """
    
    __component_name__ = "token_transfer"
    
    def __init__(
        self,
        # Chain identification
        chain_id: int,
        # Network configuration
        rpc_endpoints: List[str],
        # Monitoring settings
        polling_interval: int = 15,  # Polling interval in seconds
        max_blocks_per_scan: int = 100,  # Maximum blocks to scan per iteration
        start_block: Optional[int] = None,  # Starting block number
        # Collection settings
        token_addresses: Optional[List[str]] = None,  # Optional list of token contracts to monitor
        include_native_transfers: bool = True,  # Whether to include native token transfers
        include_erc20_transfers: bool = True,  # Whether to include ERC20 token transfers
        # Storage settings
        db_path: str = "./blockchain_state",  # Path to blockchain state storage
    ):
        """
        Initialize Token Transfer Collector for a single blockchain
        
        Args:
            chain_id: ID of the blockchain to monitor (e.g., 1 for Ethereum, 56 for BSC)
            rpc_endpoints: List of RPC endpoints for the blockchain
            polling_interval: Polling interval in seconds
            max_blocks_per_scan: Maximum blocks to scan per polling cycle
            start_block: Starting block number
            token_addresses: Token contracts to specifically monitor (optional)
            include_native_transfers: Whether to include native token transfers
            include_erc20_transfers: Whether to include ERC20 token transfers
            db_path: Path for storing blockchain state
        """
        super().__init__()
        
        if not rpc_endpoints:
            raise ValueError("At least one RPC endpoint must be provided")
        
        # Initialize parameters
        self.chain_id = chain_id
        self.polling_interval = polling_interval
        self.max_blocks_per_scan = max_blocks_per_scan
        self.start_block = start_block or 0
        self.token_addresses = token_addresses or []
        self.include_native_transfers = include_native_transfers
        self.include_erc20_transfers = include_erc20_transfers
        self.db_path = db_path
        
        # Initialize state storage
        self.state_store = BlockchainStateStore(db_path)
        
        # Create Web3 connection
        provider = AsyncMultiNodeProvider(endpoint_uri=rpc_endpoints)
        self.web3 = AsyncWeb3(provider)
        
        # Last checked block (in-memory cache)
        self.last_checked_block = 0
        
        # Known token cache
        self.token_cache: Dict[str, AsyncERC20Token] = {}
    
    async def _initialize_last_blocks(self):
        """Initialize last processed block for the chain"""
        try:
            # Create component-specific key for block tracking
            block_key = f"{self.__component_name__}:{self.chain_id}"
            
            # Get the last processed block from persistent storage
            last_block = self.state_store.get_last_processed_block(block_key)
            
            # Set starting block based on storage, config, or current block
            if last_block is not None:
                logger.info(f"Resuming from last processed block {last_block} for {block_key}")
                self.last_checked_block = last_block
            elif self.start_block > 0:
                logger.info(f"Starting from configured block {self.start_block} for {block_key}")
                self.last_checked_block = self.start_block
            else:
                # Default to current block
                try:
                    # 使用 await 获取当前区块高度
                    current_block = await self.web3.eth.block_number
                    logger.info(f"Starting from current block {current_block} for {block_key}")
                    self.last_checked_block = current_block
                except Exception as e:
                    logger.error(f"Unable to get current block for {block_key}: {e}")
                    self.last_checked_block = 0
        except Exception as e:
            logger.error(f"Error initializing last blocks for chain {self.chain_id}: {e}")
            self.last_checked_block = 0
    
    async def _start(self):
        """Collector initialization logic on startup"""
        # Initialize last blocks
        await self._initialize_last_blocks()
        
        # Verify Web3 connection
        try:
            if not await self.web3.is_connected():
                logger.warning(f"Unable to connect to network with chain ID {self.chain_id}")
        except Exception as e:
            logger.error(f"Error checking connection to network with chain ID {self.chain_id}: {e}")
        
        # Preload configured token information
        if self.token_addresses:
            for token_address in self.token_addresses:
                try:
                    token = AsyncERC20Token(self.web3, token_address)
                    # 初始化token属性
                    await token._init_properties()
                    self.token_cache[token_address.lower()] = token
                    logger.info(f"Loaded token {token.symbol} ({token_address}) on chain {self.chain_id}")
                except Exception as e:
                    logger.error(f"Error loading token {token_address} on chain {self.chain_id}: {e}")
    
    async def _stop(self):
        """Collector cleanup logic on shutdown"""
        # Close the state store
        if hasattr(self, 'state_store'):
            self.state_store.close()
    
    async def _get_token(self, token_address: str) -> Optional[AsyncERC20Token]:
        """
        Get ERC20 token instance asynchronously, using cache
        
        Args:
            token_address: Token contract address
            
        Returns:
            Optional[AsyncERC20Token]: Token instance or None
        """
        token_address = token_address.lower()
        
        # Check cache
        if token_address in self.token_cache:
            return self.token_cache[token_address]
            
        # Create new token instance
        try:
            token = AsyncERC20Token(self.web3, token_address)
            # 初始化token属性
            await token._init_properties()
            self.token_cache[token_address] = token
            return token
        except Exception as e:
            logger.error(f"Error creating token {token_address} instance on chain {self.chain_id}: {e}")
            return None

    async def _scan_erc20_transfers(self, from_block: int, to_block: int) -> AsyncGenerator[TokenTransferEvent, None]:
        """
        Scan a block range for ERC20 transfer events
        
        Args:
            from_block: Starting block
            to_block: Ending block
            
        Yields:
            TokenTransferEvent: Transfer events as they are processed
        """
        if not self.include_erc20_transfers:
            return
            
        # If no tokens specified, return
        if not self.token_addresses:
            return

        # Get logs for all specified tokens
        try:
            # Create Transfer event signature hash
            event_signature_hash = self.web3.keccak(
                text="Transfer(address,address,uint256)"
            ).hex()
            
            # Get logs for all tokens
            logs_filter = {
                'fromBlock': from_block,
                'toBlock': to_block,
                'address': [self.web3.to_checksum_address(addr) for addr in self.token_addresses],
                'topics': [event_signature_hash]
            }
            
            transfer_logs = await self.web3.eth.get_logs(logs_filter)
            
            # Process each log immediately
            for log in transfer_logs:
                try:
                    # Get token address (contract address that emitted the event)
                    token_address = log['address']
                    
                    # Get token object
                    token = await self._get_token(token_address)
                    if not token:
                        logger.warning(f"Could not get token at {token_address} on chain {self.chain_id}")
                        continue
                    
                    # Extract data from log
                    topics = log['topics']
                    
                    # Extract from and to addresses from topics
                    # Topics[0] is the event signature
                    # Topics[1] is the indexed 'from' address
                    # Topics[2] is the indexed 'to' address
                    from_address = Web3.to_checksum_address('0x' + topics[1].hex()[-40:])
                    to_address = Web3.to_checksum_address('0x' + topics[2].hex()[-40:])
                    
                    # Extract value from data (non-indexed parameter)
                    # For Transfer events, data contains just the uint256 value
                    value = int(log['data'].hex(), 16)
                    
                    # Format the value based on token decimals
                    formatted_value = value / (10 ** token.decimals)
                    
                    # Get block information for timestamp
                    block = await self.web3.eth.get_block(log['blockNumber'])
                    block_dict = dict(block) if block else {}
                    
                    # Use the helper function for safe timestamp conversion
                    timestamp = safe_timestamp_to_float(block_dict.get("timestamp"))
                    
                    if timestamp > 0:
                        block_timestamp = datetime.fromtimestamp(timestamp)
                    else:
                        # Fallback to current time if timestamp is missing
                        logger.warning(f"Missing timestamp for block {log['blockNumber']}, using current time")
                        block_timestamp = datetime.now()
                    
                    # Get transaction data to check for contract interaction
                    transaction_hash = log['transactionHash'].hex()
                    has_contract_interaction = False
                    
                    try:
                        # Get full transaction data
                        tx = await web3.eth.get_transaction(log['transactionHash'])
                        tx_dict = dict(tx) if tx else {}
                        
                        # Check if it has non-empty input data (contract interaction)
                        input_data = tx_dict.get("input", "")
                        if input_data != '0x' and input_data != '':
                            # Check if it's a simple token transfer or something more complex
                            # ERC20 token transfer function signature is a fixed pattern
                            transfer_signature = '0xa9059cbb'  # keccak256("transfer(address,uint256)") first 4 bytes
                            transferFrom_signature = '0x23b872dd'  # keccak256("transferFrom(address,address,uint256)") first 4 bytes
                            
                            # If it's not a simple token transfer, mark as contract interaction
                            if not input_data.startswith(transfer_signature) and not input_data.startswith(transferFrom_signature):
                                has_contract_interaction = True
                            # If it is a token transfer but to a contract address, it might be contract interaction
                            elif self._is_contract_address(web3, to_address):
                                has_contract_interaction = True
                    except Exception as e:
                        logger.debug(f"Error checking transaction data for contract interaction: {e}")
                    
                    # Create transfer event
                    transfer_event = TokenTransferEvent(
                        chain_id=chain_id,
                        token_address=token.address,
                        token_name=token.name,
                        token_symbol=token.symbol,
                        token_decimals=token.decimals,
                        from_address=from_address,
                        to_address=to_address,
                        value=value,
                        formatted_value=formatted_value,
                        transaction_hash=transaction_hash,
                        block_number=log['blockNumber'],
                        block_timestamp=block_timestamp,
                        log_index=log['logIndex'],
                        is_native=False,
                        has_contract_interaction=has_contract_interaction
                    )
                    
                    # Yield the event immediately
                    yield transfer_event
                except Exception as e:
                    logger.error(f"Error processing ERC20 transfer event: {e}")
        except Exception as e:
            logger.error(f"Error getting transfer logs for network {network_name}: {e}")
    
    async def _is_contract_address(self, address):
        """
        Check if an address is a contract
        
        Args:
            address: Address to check
            
        Returns:
            bool: True if the address is a contract, False otherwise
        """
        try:
            code = await self.web3.eth.get_code(address)
            return code != b'' and code != '0x'
        except Exception:
            # If we can't check, assume it's not a contract
            return False
    
    async def _scan_native_transfers(self, from_block: int, to_block: int) -> AsyncGenerator[TokenTransferEvent, None]:
        """
        Scan a block range for native token transfer events
        
        Args:
            from_block: Starting block
            to_block: Ending block
            
        Yields:
            TokenTransferEvent: Native transfer events as they are processed
        """
        if not self.include_native_transfers:
            return
        
        # Determine native token symbol based on chain ID
        native_symbol = "ETH"  # Default
        if self.chain_id == 56:
            native_symbol = "BNB"
        elif self.chain_id == 137:
            native_symbol = "MATIC"
        elif self.chain_id == 43114:
            native_symbol = "AVAX"
        
        # Process each block
        for block_num in range(from_block, to_block + 1):
            try:
                # Get block with transactions
                block = await self.web3.eth.get_block(block_num, full_transactions=True)
                
                # Skip if no transactions
                if not block or 'transactions' not in block:
                    continue
                    
                # Get block timestamp
                block_timestamp = datetime.fromtimestamp(block.get('timestamp', 0))
                
                # Process all transactions in this block
                transactions = block.get('transactions', [])
                if not transactions:
                    continue
                
                for raw_tx in transactions:
                    try:
                        # Convert transaction to dict to safely access properties
                        tx_dict = dict(raw_tx) if raw_tx else {}
                        
                        # Skip contract creation transactions
                        if tx_dict.get("to") is None:
                            continue
                            
                        # Ensure there's a value being transferred
                        value = tx_dict.get("value", 0)
                        if value == 0:
                            continue
                            
                        # Get addresses safely
                        from_address = tx_dict.get("from", "")
                        # Handle Web3.py naming differences
                        if not from_address and "from_" in tx_dict:
                            from_address = tx_dict["from_"]
                            
                        to_address = tx_dict.get("to", "")
                        
                        # Skip if invalid addresses
                        if not from_address or not to_address:
                            continue
                        
                        # Format value
                        formatted_value = float(web3.from_wei(value, 'ether'))
                        
                        # Get transaction hash
                        tx_hash = tx_dict.get("hash", None)
                        if tx_hash is None:
                            continue
                            
                        if isinstance(tx_hash, bytes):
                            transaction_hash = tx_hash.hex()
                        else:
                            transaction_hash = str(tx_hash)
                        
                        # Check if it's a contract interaction (has non-empty input data)
                        has_contract_interaction = False
                        if tx_dict.get("input", "") != '0x' and tx_dict.get("input", "") != '':
                            has_contract_interaction = True
                        
                        # Create transfer event
                        transfer_event = TokenTransferEvent(
                            chain_id=chain_id,
                            token_address=None,
                            token_name=native_symbol,
                            token_symbol=native_symbol,
                            token_decimals=18,
                            from_address=from_address,
                            to_address=to_address,
                            value=value,
                            formatted_value=formatted_value,
                            transaction_hash=transaction_hash,
                            block_number=block_num,
                            block_timestamp=block_timestamp,
                            log_index=None,
                            is_native=True,
                            has_contract_interaction=has_contract_interaction
                        )
                        
                        # Yield the event immediately
                        yield transfer_event
                    except Exception as e:
                        logger.error(f"Error processing transaction in block {block_num}: {e}")
                    
            except Exception as e:
                logger.error(f"Error scanning block {block_num} on network {network_name} for native transfers: {e}")
    
    # 修复返回类型，将异步生成器作为返回类型
    async def events(self) -> AsyncGenerator[Event, None]:
        """
        Generate event stream
        
        Polls the blockchain periodically to check for new token transfer events
        and generates TokenTransferEvent objects for ALL transfers without filtering.
        
        Yields:
            TokenTransferEvent: Token transfer event
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
                    to_block = min(current_block, from_block + self.max_blocks_per_scan - 1)
                        
                    # Create component-specific key for block tracking
                    block_key = f"{self.__component_name__}:{self.chain_id}"
                    
                    logger.info(f"Scanning chain {self.chain_id} from block {from_block} to {to_block} for {self.__component_name__}")
                    
                    # Track statistics for reporting
                    erc20_count = 0
                    native_count = 0
                    
                    # Scan and yield ERC20 transfers immediately
                    async for event in self._scan_erc20_transfers(from_block, to_block):
                        erc20_count += 1
                        yield event
                    
                    # Scan and yield native token transfers immediately
                    async for event in self._scan_native_transfers(from_block, to_block):
                        native_count += 1
                        yield event
                    
                    # Update last checked block and persist to storage with component ID
                    self.last_checked_block = to_block
                    self.state_store.set_last_processed_block(block_key, to_block)
                    
                    # Store collection statistics
                    stats = {
                        "last_processed_time": datetime.now().isoformat(),
                        "last_processed_block": to_block,
                        "events_collected": erc20_count + native_count,
                        "erc20_events": erc20_count,
                        "native_events": native_count
                    }
                    self.state_store.store_collector_stats(f"{self.__component_name__}:{self.chain_id}", stats)
                        
                    # Create a checkpoint every 1000 blocks
                    if to_block % 1000 == 0:
                        self.state_store.create_checkpoint(
                            block_key, 
                            to_block, 
                            datetime.now().isoformat()
                        )
                        
                except Exception as e:
                    logger.error(f"Error collecting token transfer events for chain {self.chain_id}: {e}")
                
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
