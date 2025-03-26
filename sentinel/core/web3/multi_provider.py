from typing import List, Dict, Any, Optional, Union, Callable, Awaitable, Sequence
import time
import random
import asyncio
from web3 import Web3, AsyncWeb3
from web3.providers.base import BaseProvider
from web3.providers.async_base import AsyncBaseProvider
from web3.providers.rpc import AsyncHTTPProvider, HTTPProvider
from web3.types import RPCEndpoint, RPCResponse
from web3.exceptions import BlockNotFound
from sentinel.logger import logger

class MultiNodeProvider(HTTPProvider):
    """
    A Web3 provider that distributes requests across multiple nodes with load balancing and failover.
    This provider can be used as a drop-in replacement for any standard Web3 provider.
    """
    
    def __init__(
        self,
        endpoint_uri: Union[str, List[str]],
        max_retries: int = 3,
        timeout: int = 10,
        rate_limit: int = 100,  # requests per second
        health_check_interval: int = 60,  # seconds
        request_kwargs: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the MultiNodeProvider.
        
        Args:
            endpoint_uri: Single RPC endpoint URL (str) or list of RPC endpoint URLs (List[str])
            max_retries: Maximum number of retry attempts per request
            timeout: Request timeout in seconds
            rate_limit: Maximum requests per second per endpoint
            health_check_interval: Interval between health checks in seconds
            request_kwargs: Additional keyword arguments to pass to the HTTP request
        """
        # Process endpoint(s)
        if isinstance(endpoint_uri, str):
            endpoints = [endpoint_uri]
        elif isinstance(endpoint_uri, list):
            endpoints = endpoint_uri
        else:
            raise TypeError("endpoint_uri must be a string or a list of strings")
            
        if not endpoints:
            raise ValueError("At least one RPC endpoint must be provided")
            
        # Prepare request kwargs
        if request_kwargs is None:
            request_kwargs = {}
            
        if 'timeout' not in request_kwargs:
            request_kwargs['timeout'] = timeout
            
        # Initialize HTTPProvider with the first endpoint
        super().__init__(endpoint_uri=endpoints[0], request_kwargs=request_kwargs)
        
        self.endpoints = endpoints
        self.max_retries = max_retries
        self.timeout = timeout
        self.rate_limit = rate_limit
        self.health_check_interval = health_check_interval
        
        # Initialize provider instances and tracking
        self.providers: List[HTTPProvider] = []
        self.last_used: Dict[str, float] = {}
        self.last_health_check: Dict[str, float] = {}
        self.node_health: Dict[str, bool] = {}
        
        # Initialize each endpoint's provider
        for endpoint in endpoints:
            provider = Web3.HTTPProvider(endpoint, request_kwargs=request_kwargs)
            self.providers.append(provider)
            self.last_used[endpoint] = 0
            self.last_health_check[endpoint] = 0
            self.node_health[endpoint] = True
            
    def _get_available_provider(self) -> Optional[HTTPProvider]:
        """Get the next available healthy provider based on rate limiting and load balancing."""
        current_time = time.time()
        
        # Shuffle providers to avoid always trying them in the same order
        available_providers = list(enumerate(self.providers))
        random.shuffle(available_providers)
        
        for idx, provider in available_providers:
            endpoint = self.endpoints[idx]
            
            # Skip unhealthy nodes
            if not self.node_health[endpoint]:
                continue
                
            # Check rate limit
            if current_time - self.last_used[endpoint] >= (1.0 / self.rate_limit):
                # Perform health check if needed
                if current_time - self.last_health_check[endpoint] >= self.health_check_interval:
                    if self._check_provider_health(provider, endpoint):
                        self.last_used[endpoint] = current_time
                        return provider
                else:
                    self.last_used[endpoint] = current_time
                    return provider
                    
        return None
        
    async def _get_available_provider_async(self) -> Optional[HTTPProvider]:
        """Async version of _get_available_provider."""
        current_time = time.time()
        
        # Shuffle providers to avoid always trying them in the same order
        available_providers = list(enumerate(self.providers))
        random.shuffle(available_providers)
        
        for idx, provider in available_providers:
            endpoint = self.endpoints[idx]
            
            # Skip unhealthy nodes
            if not self.node_health[endpoint]:
                continue
                
            # Check rate limit
            if current_time - self.last_used[endpoint] >= (1.0 / self.rate_limit):
                # Perform health check if needed
                if current_time - self.last_health_check[endpoint] >= self.health_check_interval:
                    if await self._check_provider_health_async(provider, endpoint):
                        self.last_used[endpoint] = current_time
                        return provider
                else:
                    self.last_used[endpoint] = current_time
                    return provider
                    
        return None
        
    def _check_provider_health(self, provider: HTTPProvider, endpoint: str) -> bool:
        """Check if a provider is healthy by attempting a simple request."""
        try:
            # Try to get the latest block number
            response = provider.make_request(RPCEndpoint("eth_blockNumber"), [])
            if "result" in response:
                self.last_health_check[endpoint] = time.time()
                self.node_health[endpoint] = True
                return True
            else:
                logger.warning(f"Node health check failed for {endpoint}: No result in response")
                self.node_health[endpoint] = False
                return False
        except Exception as e:
            logger.warning(f"Node health check failed for {endpoint}: {str(e)}")
            self.node_health[endpoint] = False
            return False
            
    async def _check_provider_health_async(self, provider: HTTPProvider, endpoint: str) -> bool:
        """Async version of _check_provider_health."""
        try:
            # Try to get the latest block number - use web3's request formatter
            # Some providers may have async implementations, so we use an async executor
            response = await asyncio.to_thread(
                provider.make_request, 
                RPCEndpoint("eth_blockNumber"), 
                []
            )
            
            if "result" in response:
                self.last_health_check[endpoint] = time.time()
                self.node_health[endpoint] = True
                return True
            else:
                logger.warning(f"Node health check failed for {endpoint}: No result in response")
                self.node_health[endpoint] = False
                return False
        except Exception as e:
            logger.warning(f"Node health check failed for {endpoint}: {str(e)}")
            self.node_health[endpoint] = False
            return False
            
    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        """
        Make an RPC request to an available provider with retries and failover.
        
        This method is called by Web3 for any JSON-RPC method and transparently handles
        load balancing and failover across multiple nodes.
        
        Args:
            method: The JSON-RPC method to call
            params: The parameters for the method
            
        Returns:
            The RPC response
            
        Raises:
            Exception: If all retry attempts fail
        """
        attempts = 0
        last_error = None
        
        while attempts < self.max_retries:
            provider = self._get_available_provider()
            if not provider:
                time.sleep(1.0 / self.rate_limit)  # Wait for rate limit
                attempts += 1
                continue
                
            try:
                # Make the request using the selected provider
                response = provider.make_request(method, params)
                
                # Check if we got an error response from the node
                if "error" in response:
                    endpoint = self.endpoints[self.providers.index(provider)]
                    logger.warning(f"Node {endpoint} returned error: {response['error']}")
                    # Only mark as unhealthy for serious errors
                    if "code" in response["error"] and response["error"]["code"] in [-32000, -32603, -32002]:
                        self.node_health[endpoint] = False
                    
                    # For certain errors, retry with a different node
                    attempts += 1
                    last_error = Exception(f"RPC error: {response['error']}")
                    continue
                
                return response
                
            except Exception as e:
                last_error = e
                logger.warning(f"Request failed: {str(e)}. Retrying...")
                # Mark the node as unhealthy
                endpoint = self.endpoints[self.providers.index(provider)]
                self.node_health[endpoint] = False
                attempts += 1
                
        if last_error:
            logger.error(f"All retry attempts failed: {str(last_error)}")
            raise last_error
        else:
            raise Exception("Failed to execute request after all retry attempts")
    
    async def make_request_async(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        """
        Async version of make_request.
        
        Args:
            method: The JSON-RPC method to call
            params: The parameters for the method
            
        Returns:
            The RPC response
            
        Raises:
            Exception: If all retry attempts fail
        """
        attempts = 0
        last_error = None
        
        while attempts < self.max_retries:
            provider = await self._get_available_provider_async()
            if not provider:
                await asyncio.sleep(1.0 / self.rate_limit)  # Wait for rate limit
                attempts += 1
                continue
                
            try:
                # Make the request using the selected provider
                # Use asyncio.to_thread for potentially blocking operations
                response = await asyncio.to_thread(
                    provider.make_request,
                    method,
                    params
                )
                
                # Check if we got an error response from the node
                if "error" in response:
                    endpoint = self.endpoints[self.providers.index(provider)]
                    logger.warning(f"Node {endpoint} returned error: {response['error']}")
                    # Only mark as unhealthy for serious errors
                    if "code" in response["error"] and response["error"]["code"] in [-32000, -32603, -32002]:
                        self.node_health[endpoint] = False
                    
                    # For certain errors, retry with a different node
                    attempts += 1
                    last_error = Exception(f"RPC error: {response['error']}")
                    continue
                
                return response
                
            except Exception as e:
                last_error = e
                logger.warning(f"Request failed: {str(e)}. Retrying...")
                # Mark the node as unhealthy
                endpoint = self.endpoints[self.providers.index(provider)]
                self.node_health[endpoint] = False
                attempts += 1
                
        if last_error:
            logger.error(f"All retry attempts failed: {str(last_error)}")
            raise last_error
        else:
            raise Exception("Failed to execute request after all retry attempts")
            
    def is_connected(self, show_traceback: bool = False) -> bool:
        """
        Check if at least one provider is connected and healthy.
        
        Args:
            show_traceback: If True, raise an exception with traceback when not connected
            
        Returns:
            bool: True if at least one provider is connected
        """
        for idx, provider in enumerate(self.providers):
            endpoint = self.endpoints[idx]
            
            # Skip providers already known to be unhealthy
            if not self.node_health[endpoint]:
                continue
                
            # Check if the provider is connected
            try:
                if provider.is_connected():
                    return True
            except Exception as e:
                self.node_health[endpoint] = False
                if show_traceback:
                    raise e
        
        return False
    
    async def is_connected_async(self, show_traceback: bool = False) -> bool:
        """
        Async version of is_connected.
        
        Args:
            show_traceback: If True, raise an exception with traceback when not connected
            
        Returns:
            bool: True if at least one provider is connected
        """
        for idx, provider in enumerate(self.providers):
            endpoint = self.endpoints[idx]
            
            # Skip providers already known to be unhealthy
            if not self.node_health[endpoint]:
                continue
                
            # Check if the provider is connected
            try:
                # Use asyncio.to_thread for potentially blocking operations
                result = await asyncio.to_thread(provider.is_connected)
                if result:
                    return True
            except Exception as e:
                self.node_health[endpoint] = False
                if show_traceback:
                    raise e
        
        return False


class AsyncMultiNodeProvider(AsyncHTTPProvider):
    """
    An async version of MultiNodeProvider that implements the async provider interface
    required by AsyncWeb3. This provider also handles load balancing and failover.
    """
    
    def __init__(
        self,
        endpoint_uri: Union[str, List[str]],
        max_retries: int = 3,
        timeout: int = 10,
        rate_limit: int = 100,  # requests per second
        health_check_interval: int = 60,  # seconds
        request_kwargs: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the AsyncMultiNodeProvider.
        
        Args:
            endpoint_uri: Single RPC endpoint URL (str) or list of RPC endpoint URLs (List[str])
            max_retries: Maximum number of retry attempts per request
            timeout: Request timeout in seconds
            rate_limit: Maximum requests per second per endpoint
            health_check_interval: Interval between health checks in seconds
            request_kwargs: Additional keyword arguments to pass to the HTTP request
        """
        # Process endpoint(s)
        if isinstance(endpoint_uri, str):
            endpoints = [endpoint_uri]
        elif isinstance(endpoint_uri, list):
            endpoints = endpoint_uri
        else:
            raise TypeError("endpoint_uri must be a string or a list of strings")
            
        if not endpoints:
            raise ValueError("At least one RPC endpoint must be provided")
            
        # Prepare request kwargs
        if request_kwargs is None:
            request_kwargs = {}
            
        if 'timeout' not in request_kwargs:
            request_kwargs['timeout'] = timeout
            
        # Initialize AsyncHTTPProvider with the first endpoint
        super().__init__(endpoint_uri=endpoints[0], request_kwargs=request_kwargs)
        
        # Create the underlying MultiNodeProvider for the actual multi-node functionality
        self.multi_provider = MultiNodeProvider(
            endpoint_uri=endpoints,
            max_retries=max_retries,
            timeout=timeout,
            rate_limit=rate_limit,
            health_check_interval=health_check_interval,
            request_kwargs=request_kwargs
        )
    
    def make_request(self, method: RPCEndpoint, params: Any) -> RPCResponse:
        """
        Synchronous request method, delegates to the MultiNodeProvider.
        This is needed for the BaseProvider interface.
        """
        return self.multi_provider.make_request(method, params)
    
    async def make_request(self, method: RPCEndpoint, params: Sequence[Any]) -> RPCResponse:
        """
        Asynchronous request method required by AsyncHTTPProvider.
        
        Args:
            method: The JSON-RPC method to call
            params: The parameters for the method
            
        Returns:
            The RPC response
        """
        return await self.multi_provider.make_request_async(method, params)
    
    def is_connected(self, show_traceback: bool = False) -> bool:
        """
        Check if the provider is connected to at least one healthy node.
        
        Args:
            show_traceback: If True, raise an exception with traceback when not connected
            
        Returns:
            bool: True if connected
        """
        return self.multi_provider.is_connected(show_traceback=show_traceback)
    
    async def is_connected(self, show_traceback: bool = False) -> bool:
        """
        Async version of is_connected.
        
        Args:
            show_traceback: If True, raise an exception with traceback when not connected
            
        Returns:
            bool: True if connected
        """
        return await self.multi_provider.is_connected_async(show_traceback=show_traceback)
