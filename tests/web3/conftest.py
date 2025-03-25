import pytest
from unittest.mock import Mock
from web3 import Web3
from web3.contract import Contract

@pytest.fixture
def mock_web3():
    """Create a mock Web3 instance."""
    mock = Mock(spec=Web3)
    mock.eth = Mock()
    return mock

@pytest.fixture
def mock_contract():
    """Create a mock ERC20 contract."""
    mock = Mock(spec=Contract)
    mock.functions = Mock()
    return mock

@pytest.fixture
def mock_transfer_event():
    """Create a mock transfer event."""
    return {
        "args": {
            "from": "0xabc",
            "to": "0xdef",
            "value": 1000 * 10**18  # 1000 tokens
        },
        "blockNumber": 123456,
        "transactionHash": "0x123"
    }

@pytest.fixture
def mock_token_info():
    """Create mock token information."""
    return {
        "name": "Test Token",
        "symbol": "TEST",
        "decimals": 18,
        "address": "0x123"
    } 