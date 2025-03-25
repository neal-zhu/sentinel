from typing import List, Optional, Any, Dict
import time
import random
from web3 import Web3
from web3.exceptions import BlockNotFound
from web3.types import BlockData, TxData
from eth_typing import Address
from sentinel.logger import logger

class NodeManager:
    """Manages multiple Web3 nodes with load balancing and rate limiting."""
    
    def __init__(
        self,
        rpc_endpoints: List[str],
        max_retries: int = 3,
        timeout: int = 10,
        rate_limit: int = 100,  # requests per second
        health_check_interval: int = 60  # seconds
    ):
        """
        Initialize the NodeManager.
        
        Args:
            rpc_endpoints: List of RPC endpoint URLs
            max_retries: Maximum number of retry attempts per request
            timeout: Request timeout in seconds
            rate_limit: Maximum requests per second per endpoint
            health_check_interval: Interval between health checks in seconds
        """
        self.endpoints = rpc_endpoints
        self.max_retries = max_retries
        self.timeout = timeout
        self.rate_limit = rate_limit
        self.health_check_interval = health_check_interval
        
        # Initialize Web3 instances and tracking
        self.web3_instances: List[Web3] = []
        self.last_used: Dict[str, float] = {}
        self.last_health_check: Dict[str, float] = {}
        self.node_health: Dict[str, bool] = {}
        
        # Initialize each endpoint
        for endpoint in rpc_endpoints:
            w3 = Web3(Web3.HTTPProvider(endpoint, request_kwargs={'timeout': timeout}))
            self.web3_instances.append(w3)
            self.last_used[endpoint] = 0
            self.last_health_check[endpoint] = 0
            self.node_health[endpoint] = True
            
    async def _get_available_node(self) -> Optional[Web3]:
        """Get the next available healthy node based on rate limiting and round-robin."""
        current_time = time.time()
        
        # Shuffle endpoints to avoid always trying them in the same order
        available_instances = list(enumerate(self.web3_instances))
        random.shuffle(available_instances)
        
        for idx, w3 in available_instances:
            endpoint = self.endpoints[idx]
            
            # Skip unhealthy nodes
            if not self.node_health[endpoint]:
                continue
                
            # Check rate limit
            if current_time - self.last_used[endpoint] >= (1.0 / self.rate_limit):
                # Perform health check if needed
                if current_time - self.last_health_check[endpoint] >= self.health_check_interval:
                    if await self._check_node_health(w3, endpoint):
                        self.last_used[endpoint] = current_time
                        return w3
                else:
                    self.last_used[endpoint] = current_time
                    return w3
                    
        return None
        
    async def _check_node_health(self, w3: Web3, endpoint: str) -> bool:
        """Check if a node is healthy by attempting a simple request."""
        try:
            # Try to get the latest block number
            await w3.eth.get_block_number()
            self.last_health_check[endpoint] = time.time()
            self.node_health[endpoint] = True
            return True
        except Exception as e:
            logger.warning(f"Node health check failed for {endpoint}: {str(e)}")
            self.node_health[endpoint] = False
            return False
            
    async def execute_request(self, method: str, *args, **kwargs) -> Any:
        """
        Execute a Web3 request with retries and failover.
        
        Args:
            method: The Web3 method to call (e.g., 'get_block', 'get_transaction')
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method
            
        Returns:
            The result of the Web3 method call
            
        Raises:
            Exception: If all retry attempts fail
        """
        attempts = 0
        last_error = None
        
        while attempts < self.max_retries:
            w3 = await self._get_available_node()
            if not w3:
                time.sleep(1.0 / self.rate_limit)  # Wait for rate limit
                attempts += 1
                continue
                
            try:
                # Get the method from web3 instance dynamically
                method_to_call = getattr(w3.eth, method)
                result = await method_to_call(*args, **kwargs)
                return result
                
            except Exception as e:
                last_error = e
                logger.warning(f"Request failed: {str(e)}. Retrying...")
                # Mark the node as unhealthy
                endpoint = self.endpoints[self.web3_instances.index(w3)]
                self.node_health[endpoint] = False
                attempts += 1
                
        if last_error:
            logger.error(f"All retry attempts failed: {str(last_error)}")
            raise last_error
        else:
            raise Exception("Failed to execute request after all retry attempts")
            
    async def get_block(self, block_identifier: str = 'latest') -> BlockData:
        """Get a block by its identifier."""
        return await self.execute_request('get_block', block_identifier)
        
    async def get_transaction(self, tx_hash: str) -> TxData:
        """Get a transaction by its hash."""
        return await self.execute_request('get_transaction', tx_hash)
        
    async def get_transaction_receipt(self, tx_hash: str) -> Dict[str, Any]:
        """Get a transaction receipt by its hash."""
        return await self.execute_request('get_transaction_receipt', tx_hash)
        
    async def get_balance(self, address: str) -> int:
        """Get the balance of an address."""
        return await self.execute_request('get_balance', address) 