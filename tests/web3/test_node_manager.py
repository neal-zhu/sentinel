import pytest
from unittest.mock import Mock, patch, AsyncMock
from web3 import Web3
from web3.exceptions import BlockNotFound
from web3.providers.base import BaseProvider

from sentinel.core.web3.node_manager import NodeManager

@pytest.fixture
def mock_provider():
    """Create a mock Web3 provider."""
    provider = Mock(spec=BaseProvider)
    return provider

@pytest.fixture
def node_manager(mock_provider):
    """Create a NodeManager instance with mocked Web3."""
    with patch('web3.Web3.HTTPProvider', return_value=mock_provider):
        manager = NodeManager(
            rpc_endpoints=["http://test1", "http://test2"],
            max_retries=2,
            timeout=1,
            rate_limit=10
        )
        # Mock eth attribute for all web3 instances
        for w3 in manager.web3_instances:
            w3.eth = AsyncMock()
            w3.eth.get_block = AsyncMock(return_value={"number": 1})
            w3.eth.get_transaction = AsyncMock(return_value={"hash": "0x123"})
            w3.eth.get_balance = AsyncMock(return_value=1000000000000000000)
            w3.eth.get_block_number = AsyncMock(return_value=123)
        return manager

@pytest.mark.asyncio
async def test_initialization(node_manager):
    """Test NodeManager initialization."""
    assert len(node_manager.web3_instances) == 2
    assert len(node_manager.endpoints) == 2
    assert node_manager.max_retries == 2
    assert node_manager.timeout == 1
    assert node_manager.rate_limit == 10

@pytest.mark.asyncio
async def test_get_available_node(node_manager):
    """Test node selection with load balancing."""
    # First call should return first node
    node1 = await node_manager._get_available_node()
    assert node1 is not None
    
    # Second call should return second node due to rate limiting
    node2 = await node_manager._get_available_node()
    assert node2 is not None
    assert node2 != node1

@pytest.mark.asyncio
async def test_health_check(node_manager):
    """Test node health checking."""
    # Test healthy node
    node_manager.web3_instances[0].eth.get_block_number.return_value = 123
    assert await node_manager._check_node_health(node_manager.web3_instances[0], "http://test1")
    
    # Test unhealthy node
    node_manager.web3_instances[0].eth.get_block_number.side_effect = Exception("Node down")
    assert not await node_manager._check_node_health(node_manager.web3_instances[0], "http://test1")

@pytest.mark.asyncio
async def test_execute_request_success(node_manager):
    """Test successful request execution."""
    result = await node_manager.execute_request("get_block", "latest")
    assert result == {"number": 1}

@pytest.mark.asyncio
async def test_execute_request_retry(node_manager):
    """Test request retry on failure."""
    # Mock first node to fail, second node to succeed
    node_manager.web3_instances[0].eth.get_block.side_effect = Exception("Timeout")
    node_manager.web3_instances[1].eth.get_block.return_value = {"number": 1}
    
    result = await node_manager.execute_request("get_block", "latest")
    assert result == {"number": 1}
    
    # Verify that at least one node was tried and the request succeeded
    total_calls = (node_manager.web3_instances[0].eth.get_block.call_count +
                  node_manager.web3_instances[1].eth.get_block.call_count)
    assert total_calls >= 1  # At least one node was tried
    assert node_manager.web3_instances[1].eth.get_block.call_count >= 1  # Success node was called

@pytest.mark.asyncio
async def test_execute_request_max_retries(node_manager):
    """Test max retries exceeded."""
    # Mock both nodes to fail consistently
    for w3 in node_manager.web3_instances:
        w3.eth.get_block.side_effect = Exception("Timeout")
    
    with pytest.raises(Exception):
        await node_manager.execute_request("get_block", "latest")
    
    # Verify each node was tried at least once
    assert node_manager.web3_instances[0].eth.get_block.call_count >= 1
    assert node_manager.web3_instances[1].eth.get_block.call_count >= 1

@pytest.mark.asyncio
async def test_get_block(node_manager):
    """Test get_block method."""
    result = await node_manager.get_block("latest")
    assert result == {"number": 1}

@pytest.mark.asyncio
async def test_get_transaction(node_manager):
    """Test get_transaction method."""
    result = await node_manager.get_transaction("0x123")
    assert result == {"hash": "0x123"}

@pytest.mark.asyncio
async def test_get_balance(node_manager):
    """Test get_balance method."""
    result = await node_manager.get_balance("0x123")
    assert result == 1000000000000000000 