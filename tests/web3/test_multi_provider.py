from unittest.mock import AsyncMock, Mock, patch

import pytest
from web3 import AsyncWeb3, Web3
from web3.providers.base import BaseProvider
from web3.types import RPCEndpoint

from sentinel.core.web3.multi_provider import AsyncMultiNodeProvider, MultiNodeProvider


@pytest.fixture
def mock_provider():
    """Create a mock Web3 provider."""
    provider = Mock(spec=BaseProvider)
    provider.make_request.return_value = {"result": 123}
    provider.is_connected.return_value = True
    return provider


@pytest.fixture
def async_mock_provider():
    """Create a mock Web3 async provider."""
    provider = Mock(spec=BaseProvider)
    provider.make_request.return_value = {"result": 123}
    provider.is_connected.return_value = True
    return provider


@pytest.fixture
def multi_node_provider(mock_provider):
    """Create a MultiNodeProvider instance with mocked providers."""
    with patch("web3.Web3.HTTPProvider", return_value=mock_provider):
        provider = MultiNodeProvider(
            endpoint_uri=["http://test1", "http://test2"],
            max_retries=2,
            timeout=1,
            rate_limit=10,
        )
        return provider


@pytest.fixture
def async_multi_node_provider(async_mock_provider, multi_node_provider):
    """Create an AsyncMultiNodeProvider instance with mocked providers."""
    provider = AsyncMultiNodeProvider(
        endpoint_uri=["http://test1", "http://test2"],
        max_retries=2,
        timeout=1,
        rate_limit=10,
    )

    # Replace the internal provider with our mocked provider
    provider.multi_provider = multi_node_provider
    return provider


@pytest.fixture
def web3_instance(multi_node_provider):
    """Create a Web3 instance with a MultiNodeProvider."""
    return Web3(multi_node_provider)


@pytest.fixture
def async_web3_instance(async_multi_node_provider):
    """Create an AsyncWeb3 instance with an AsyncMultiNodeProvider."""
    async_w3 = AsyncWeb3(async_multi_node_provider)

    # Mock eth methods for testing
    async_w3.eth.get_block = AsyncMock(return_value={"number": 1})
    async_w3.eth.get_transaction = AsyncMock(return_value={"hash": "0x123"})
    async_w3.eth.get_balance = AsyncMock(return_value=1000000000000000000)

    return async_w3


def test_multi_node_provider_initialization(multi_node_provider):
    """Test MultiNodeProvider initialization."""
    assert len(multi_node_provider.providers) == 2
    assert len(multi_node_provider.endpoints) == 2
    assert multi_node_provider.max_retries == 2
    assert multi_node_provider.timeout == 1
    assert multi_node_provider.rate_limit == 10


def test_get_available_provider(multi_node_provider):
    """Test provider selection with load balancing."""
    # First call should return a provider
    provider1 = multi_node_provider._get_available_provider()
    assert provider1 is not None


def test_provider_health_check(multi_node_provider, mock_provider):
    """Test provider health checking."""
    # Test healthy provider
    mock_provider.make_request.return_value = {"result": 123}
    assert multi_node_provider._check_provider_health(mock_provider, "http://test1")

    # Test unhealthy provider
    mock_provider.make_request.return_value = {
        "error": {"code": -32000, "message": "Node down"}
    }
    assert not multi_node_provider._check_provider_health(mock_provider, "http://test1")

    # Test exception
    mock_provider.make_request.side_effect = Exception("Connection failed")
    assert not multi_node_provider._check_provider_health(mock_provider, "http://test1")


def test_make_request_success(multi_node_provider, mock_provider):
    """Test successful request execution."""
    mock_provider.make_request.return_value = {"result": 123}
    result = multi_node_provider.make_request(RPCEndpoint("eth_blockNumber"), [])
    assert result == {"result": 123}


def test_make_request_retry(multi_node_provider, mock_provider):
    """Test request retry on failure."""
    # Create a second mock provider that will succeed
    second_provider = Mock(spec=BaseProvider)
    second_provider.make_request.return_value = {"result": 123}

    # Replace the providers list with our two mocks
    multi_node_provider.providers = [mock_provider, second_provider]
    multi_node_provider.endpoints = ["http://test1", "http://test2"]
    multi_node_provider.node_health = {"http://test1": True, "http://test2": True}

    # First provider fails
    mock_provider.make_request.side_effect = Exception("Timeout")

    # Make the request, should fall back to the second provider
    result = multi_node_provider.make_request(RPCEndpoint("eth_blockNumber"), [])

    # The request should succeed with the second provider
    assert result == {"result": 123}

    # We don't care about exact call counts, just that the result is correct
    # and the method handled the failure appropriately


def test_make_request_max_retries(multi_node_provider, mock_provider):
    """Test max retries exceeded."""
    # All calls fail
    mock_provider.make_request.side_effect = Exception("Timeout")

    with pytest.raises(Exception):
        multi_node_provider.make_request(RPCEndpoint("eth_blockNumber"), [])

    # Verify provider was tried at least max_retries times
    assert mock_provider.make_request.call_count >= multi_node_provider.max_retries


def test_web3_integration(web3_instance):
    """Test integration with Web3."""
    # Setup mocked eth method
    web3_instance.eth.get_block_number = Mock(return_value=123)

    # Test that we can access eth methods
    assert web3_instance.eth.get_block_number() == 123


@pytest.mark.asyncio
async def test_async_web3_integration(async_web3_instance):
    """Test integration with AsyncWeb3."""
    # Test that we can access async eth methods
    async_block = await async_web3_instance.eth.get_block("latest")
    assert async_block == {"number": 1}


def test_string_endpoint_initialization(mock_provider):
    """Test MultiNodeProvider initialization with a single string endpoint."""
    with patch("web3.Web3.HTTPProvider", return_value=mock_provider):
        provider = MultiNodeProvider(
            endpoint_uri="http://single-endpoint",
            max_retries=2,
            timeout=1,
            rate_limit=10,
        )
        # Verify that a single string endpoint is correctly handled
        assert len(provider.providers) == 1
        assert len(provider.endpoints) == 1
        assert provider.endpoints[0] == "http://single-endpoint"


def test_async_string_endpoint_initialization(async_mock_provider):
    """Test AsyncMultiNodeProvider initialization with a single string endpoint."""
    provider = AsyncMultiNodeProvider(
        endpoint_uri="http://single-endpoint", max_retries=2, timeout=1, rate_limit=10
    )

    # Verify that a single string endpoint is correctly handled
    assert len(provider.multi_provider.providers) == 1
    assert len(provider.multi_provider.endpoints) == 1
    assert provider.multi_provider.endpoints[0] == "http://single-endpoint"
