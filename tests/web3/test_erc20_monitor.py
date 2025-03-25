import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
from web3 import Web3
from web3.providers.base import BaseProvider

from sentinel.core.web3.node_manager import NodeManager
from sentinel.core.web3.erc20_monitor import ERC20Monitor

@pytest.fixture
def mock_provider():
    """Create a mock Web3 provider."""
    provider = Mock(spec=BaseProvider)
    return provider

@pytest.fixture
def mock_node_manager(mock_provider):
    """Create a NodeManager instance with mocked Web3."""
    with patch('web3.Web3.HTTPProvider', return_value=mock_provider):
        manager = NodeManager(
            rpc_endpoints=["http://test1"],
            max_retries=2,
            timeout=1,
            rate_limit=10
        )
        # Mock eth attribute for all web3 instances
        for w3 in manager.web3_instances:
            w3.eth = AsyncMock()
            w3.eth.contract = Mock()
        return manager

@pytest.fixture
def mock_contract():
    """Create a mock ERC20 contract."""
    contract = Mock()
    contract.functions = Mock()
    contract.functions.name = Mock(return_value=Mock(call=AsyncMock(return_value="Test Token")))
    contract.functions.symbol = Mock(return_value=Mock(call=AsyncMock(return_value="TEST")))
    contract.functions.decimals = Mock(return_value=Mock(call=AsyncMock(return_value=18)))
    return contract

@pytest.fixture
def erc20_monitor(mock_node_manager, mock_contract):
    """Create an ERC20Monitor instance with mocked dependencies."""
    with patch('web3.Web3.to_checksum_address', side_effect=lambda x: x):
        mock_node_manager.web3_instances[0].eth.contract.return_value = mock_contract
        monitor = ERC20Monitor(
            node_manager=mock_node_manager,
            token_address="0x123",
            min_amount=1000.0,
            time_window=3600
        )
        # Initialize required attributes
        monitor.decimals = 18
        monitor.symbol = "TEST"
        monitor.name = "Test Token"
        return monitor

@pytest.mark.asyncio
async def test_initialization(erc20_monitor):
    """Test ERC20Monitor initialization."""
    assert erc20_monitor.token_address == "0x123"
    assert erc20_monitor.min_amount == 1000.0
    assert erc20_monitor.time_window == 3600

@pytest.mark.asyncio
async def test_initialize(erc20_monitor, mock_contract):
    """Test token information initialization."""
    await erc20_monitor.initialize()
    assert erc20_monitor.decimals == 18
    assert erc20_monitor.symbol == "TEST"
    assert erc20_monitor.name == "Test Token"

@pytest.mark.asyncio
async def test_is_significant_transfer(erc20_monitor):
    """Test transfer significance check."""
    erc20_monitor.decimals = 18
    # Test significant transfer
    assert erc20_monitor._is_significant_transfer(2000 * 10**18)  # 2000 tokens
    # Test insignificant transfer
    assert not erc20_monitor._is_significant_transfer(500 * 10**18)  # 500 tokens

@pytest.mark.asyncio
async def test_update_address_stats(erc20_monitor):
    """Test address statistics update."""
    transfer = {
        "from": "0xabc",
        "to": "0xdef",
        "value": 1500 * 10**18,  # 1500 tokens
        "block_number": int(datetime.now().timestamp())
    }
    
    erc20_monitor._update_address_stats(transfer)
    
    # Check sender stats
    assert erc20_monitor.address_stats["0xabc"]["total_volume"] == 1500 * 10**18
    assert erc20_monitor.address_stats["0xabc"]["transfer_count"] == 1
    
    # Check receiver stats
    assert erc20_monitor.address_stats["0xdef"]["total_volume"] == 1500 * 10**18
    assert erc20_monitor.address_stats["0xdef"]["transfer_count"] == 1

@pytest.mark.asyncio
async def test_cleanup_old_data(erc20_monitor):
    """Test data cleanup."""
    now = datetime.now()
    erc20_monitor.address_stats = {
        "0x1": {
            "total_volume": 1000 * 10**18,
            "transfer_count": 1,
            "last_transfer": now - timedelta(hours=2)
        },
        "0x2": {
            "total_volume": 2000 * 10**18,
            "transfer_count": 2,
            "last_transfer": now
        }
    }
    
    erc20_monitor._cleanup_old_data()
    
    assert "0x1" not in erc20_monitor.address_stats
    assert "0x2" in erc20_monitor.address_stats

@pytest.mark.asyncio
async def test_analyze_patterns(erc20_monitor):
    """Test pattern analysis."""
    now = datetime.now()
    erc20_monitor.address_stats = {
        "0x1": {
            "total_volume": 10000 * 10**18,
            "transfer_count": 15,
            "last_transfer": now,
            "protocol_interactions": 2
        },
        "0x2": {
            "total_volume": 500 * 10**18,
            "transfer_count": 1,
            "last_transfer": now,
            "protocol_interactions": 0
        }
    }
    
    signals = erc20_monitor.analyze_patterns()
    assert len(signals) == 1
    assert signals[0]["address"] == "0x1"
    assert signals[0]["protocol_interactions"] == 2

@pytest.mark.asyncio
async def test_process_transfer_event(erc20_monitor):
    """Test transfer event processing."""
    event = {
        "args": {
            "from": "0xsender",
            "to": "0xreceiver",
            "value": 2000 * 10**18  # 2000 tokens
        },
        "blockNumber": int(datetime.now().timestamp()),
        "transactionHash": bytes.fromhex("1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef")
    }
    
    await erc20_monitor.process_transfer_event(event)
    
    # Check sender stats
    assert erc20_monitor.address_stats["0xsender"]["total_volume"] == 2000 * 10**18
    assert erc20_monitor.address_stats["0xsender"]["transfer_count"] == 1
    
    # Check receiver stats
    assert erc20_monitor.address_stats["0xreceiver"]["total_volume"] == 2000 * 10**18
    assert erc20_monitor.address_stats["0xreceiver"]["transfer_count"] == 1 