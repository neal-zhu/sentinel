import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from sentinel.strategies.token_movement import TokenMovementStrategy
from sentinel.core.events import TokenTransferEvent
from sentinel.core.alerts import Alert

@pytest.fixture
def token_transfer_event():
    """Create a sample token transfer event for testing"""
    return TokenTransferEvent(
        chain_id=1,
        token_address='0x1234567890123456789012345678901234567890',
        token_name='Test Token',
        token_symbol='TEST',
        token_decimals=18,
        from_address='0xSender',
        to_address='0xReceiver',
        value=1000000000000000000,
        formatted_value=100.0,
        transaction_hash='0xabcdef',
        block_number=1000001,
        block_timestamp=datetime.now(),
        log_index=0,
        is_native=False
    )

@pytest.fixture
def token_movement_strategy():
    """Create a token movement strategy for testing"""
    strategy = TokenMovementStrategy(
        significant_transfer_threshold={
            '1': {  # Ethereum
                'TEST': 50.0,  # Significant threshold for TEST token
                'ETH': 1.0     # Significant threshold for ETH
            }
        },
        watch_addresses={
            '1': ['0xWatched1', '0xWatched2']
        },
        watch_tokens={
            '1': ['0x1234567890123456789012345678901234567890']
        },
        alert_cooldown=0  # No cooldown for easier testing
    )
    return strategy

@pytest.mark.asyncio
async def test_strategy_initialization(token_movement_strategy):
    """Test strategy initialization"""
    # Verify initialization
    assert token_movement_strategy.__component_name__ == "token_movement"
    assert '1' in token_movement_strategy.significant_transfer_threshold
    assert '1' in token_movement_strategy.watch_addresses
    assert '1' in token_movement_strategy.watch_tokens

@pytest.mark.asyncio
async def test_is_significant_transfer(token_movement_strategy, token_transfer_event):
    """Test _is_significant_transfer method"""
    # Test with a value above threshold
    assert token_movement_strategy._is_significant_transfer(token_transfer_event) == True
    
    # Test with a value below threshold
    small_transfer = TokenTransferEvent(
        chain_id=1,
        token_address='0x1234567890123456789012345678901234567890',
        token_name='Test Token',
        token_symbol='TEST',
        token_decimals=18,
        from_address='0xSender',
        to_address='0xReceiver',
        value=10000000000000000,  # 0.01 ETH
        formatted_value=10.0,     # Below threshold
        transaction_hash='0xabcdef',
        block_number=1000001,
        block_timestamp=datetime.now(),
        log_index=0,
        is_native=False
    )
    assert token_movement_strategy._is_significant_transfer(small_transfer) == False
    
    # Test with a token not in threshold list
    unknown_token = TokenTransferEvent(
        chain_id=1,
        token_address='0x9999999999999999999999999999999999999999',
        token_name='Unknown Token',
        token_symbol='UNK',
        token_decimals=18,
        from_address='0xSender',
        to_address='0xReceiver',
        value=1000000000000000000,
        formatted_value=100.0,
        transaction_hash='0xabcdef',
        block_number=1000001,
        block_timestamp=datetime.now(),
        log_index=0,
        is_native=False
    )
    assert token_movement_strategy._is_significant_transfer(unknown_token) == True
    
    # Test with a chain not in threshold list
    other_chain = TokenTransferEvent(
        chain_id=56,  # BSC
        token_address='0x1234567890123456789012345678901234567890',
        token_name='Test Token',
        token_symbol='TEST',
        token_decimals=18,
        from_address='0xSender',
        to_address='0xReceiver',
        value=1000000000000000000,
        formatted_value=100.0,
        transaction_hash='0xabcdef',
        block_number=1000001,
        block_timestamp=datetime.now(),
        log_index=0,
        is_native=False
    )
    assert token_movement_strategy._is_significant_transfer(other_chain) == True

@pytest.mark.asyncio
async def test_analyze_large_transfer(token_movement_strategy, token_transfer_event):
    """Test that a large transfer generates an alert"""
    alerts = await token_movement_strategy.analyze(token_transfer_event)
    
    # Should generate at least one alert
    assert len(alerts) > 0
    
    # Find the significant transfer alert
    significant_alerts = [a for a in alerts if "Significant Token Transfer" in a.title]
    assert len(significant_alerts) > 0
    
    # Verify alert details
    alert = significant_alerts[0]
    assert alert.severity == "medium"
    assert alert.source == "token_movement_strategy"
    assert alert.data["token_symbol"] == "TEST"
    assert alert.data["formatted_value"] == 100.0

@pytest.mark.asyncio
async def test_watched_address(token_movement_strategy):
    """Test that transfers involving watched addresses are detected"""
    # Create event with watched address
    watched_address_event = TokenTransferEvent(
        chain_id=1,
        token_address='0x1234567890123456789012345678901234567890',
        token_name='Test Token',
        token_symbol='TEST',
        token_decimals=18,
        from_address='0xWatched1',  # Watched address
        to_address='0xReceiver',
        value=100000000000000000,  # Small amount
        formatted_value=10.0,       # Below threshold
        transaction_hash='0xabcdef',
        block_number=1000001,
        block_timestamp=datetime.now(),
        log_index=0,
        is_native=False
    )
    
    # Should still alert because of watched address, even though value is below threshold
    alerts = await token_movement_strategy.analyze(watched_address_event)
    
    # Find alerts related to the watched address
    significant_alerts = [a for a in alerts if "Significant Token Transfer" in a.title]
    assert len(significant_alerts) > 0
    
    # Verify alert details
    alert = significant_alerts[0]
    assert alert.data["from_watched"] == True
    assert alert.data["from_address"] == "0xWatched1"

@pytest.mark.asyncio
async def test_unusual_transfer_detection(token_movement_strategy):
    """Test detection of unusual transfers compared to baseline"""
    # First, create a baseline of "normal" transfers
    normal_value = 10.0
    
    # Generate 50 "normal" transfers
    for i in range(50):
        event = TokenTransferEvent(
            chain_id=1,
            token_address='0x1234567890123456789012345678901234567890',
            token_name='Test Token',
            token_symbol='TEST',
            token_decimals=18,
            from_address=f'0xSender{i}',
            to_address=f'0xReceiver{i}',
            value=int(normal_value * 10**18),
            formatted_value=normal_value,
            transaction_hash=f'0xabcdef{i}',
            block_number=1000001 + i,
            block_timestamp=datetime.now() - timedelta(hours=1) + timedelta(minutes=i),
            log_index=i,
            is_native=False
        )
        await token_movement_strategy.analyze(event)
    
    # Now create an unusually large transfer
    unusual_event = TokenTransferEvent(
        chain_id=1,
        token_address='0x1234567890123456789012345678901234567890',
        token_name='Test Token',
        token_symbol='TEST',
        token_decimals=18,
        from_address='0xSenderUnusual',
        to_address='0xReceiverUnusual',
        value=int(normal_value * 100 * 10**18),  # 100x normal value
        formatted_value=normal_value * 100,
        transaction_hash='0xabcdefUnusual',
        block_number=1000100,
        block_timestamp=datetime.now(),
        log_index=0,
        is_native=False
    )
    
    alerts = await token_movement_strategy.analyze(unusual_event)
    
    # Should generate both a significant transfer alert and an unusual transfer alert
    unusual_alerts = [a for a in alerts if "Unusual Token Transfer" in a.title]
    assert len(unusual_alerts) > 0
    
    # Verify alert details
    alert = unusual_alerts[0]
    assert alert.severity == "medium"
    assert "standard deviations" in alert.description or "average transfer size" in alert.description 