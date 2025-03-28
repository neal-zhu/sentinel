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
        blacklist_addresses={
            '1': ['0xBlacklisted1', '0xBlacklisted2']
        },
        alert_cooldown=0  # No cooldown for easier testing
    )
    return strategy

@pytest.mark.asyncio
async def test_is_blacklisted_address(token_movement_strategy):
    """Test _is_blacklisted_address method"""
    # Test with a blacklisted address
    assert token_movement_strategy._is_blacklisted_address(1, '0xBlacklisted1') == True
    assert token_movement_strategy._is_blacklisted_address(1, '0xblacklisted2') == True  # Case insensitive
    
    # Test with a non-blacklisted address
    assert token_movement_strategy._is_blacklisted_address(1, '0xNonBlacklisted') == False
    
    # Test with a chain not in the blacklist
    assert token_movement_strategy._is_blacklisted_address(56, '0xBlacklisted1') == False

@pytest.mark.asyncio
async def test_is_unusual_transfer(token_movement_strategy, token_transfer_event):
    """Test _is_unusual_transfer method"""
    # Initially, with no history, it should not be unusual
    assert token_movement_strategy._is_unusual_transfer(token_transfer_event) == False
    
    # Add the event to token stats to build history
    token_key = (token_transfer_event.chain_id, token_transfer_event.token_address)
    token_movement_strategy.token_stats[token_key] = {
        'mean_value': 10.0,
        'stdev_value': 5.0,
        'transfer_count': 100,  # > anomaly_window_size
    }
    
    # Now with stats in place, test normal and unusual transfers
    # This transfer is (100 - 10) / 5 = 18 standard deviations from mean, highly unusual
    assert token_movement_strategy._is_unusual_transfer(token_transfer_event) == True
    
    # Create a normal transfer within expected range
    normal_event = TokenTransferEvent(
        chain_id=1,
        token_address='0x1234567890123456789012345678901234567890',
        token_name='Test Token',
        token_symbol='TEST',
        token_decimals=18,
        from_address='0xSender',
        to_address='0xReceiver',
        value=100000000000000000,  # 0.1 ETH
        formatted_value=12.0,     # Close to mean
        transaction_hash='0xabcdef',
        block_number=1000001,
        block_timestamp=datetime.now(),
        log_index=0,
        is_native=False
    )
    # This transfer is (12 - 10) / 5 = 0.4 standard deviations from mean, normal
    assert token_movement_strategy._is_unusual_transfer(normal_event) == False

@pytest.mark.asyncio
async def test_process_event(token_movement_strategy, token_transfer_event):
    """Test process_event method"""
    # Test with standard token transfer event
    alerts = await token_movement_strategy.process_event(token_transfer_event)
    
    # Process a non-TokenTransferEvent
    class OtherEvent:
        pass
    
    other_event = OtherEvent()
    alerts = await token_movement_strategy.process_event(other_event)
    assert alerts == []

@pytest.mark.asyncio
async def test_generate_report(token_movement_strategy, token_transfer_event):
    """Test _generate_report method"""
    # Initially with no data, should not generate a report
    report = await token_movement_strategy._generate_report()
    assert report is None
    
    # Add some token stats and address stats
    chain_id = token_transfer_event.chain_id
    token_addr = token_transfer_event.token_address
    token_key = (chain_id, token_addr)
    
    token_movement_strategy.token_stats[token_key] = {
        'token_symbol': 'TEST',
        'total_volume': 1000.0,
        'transfer_count': 10,
        'avg_transfer': 100.0
    }
    
    sender_key = (chain_id, token_transfer_event.from_address)
    token_movement_strategy.address_stats[sender_key] = {
        'sent_count': 5,
        'received_count': 3,
        'total_sent': 500.0,
        'total_received': 300.0,
        'tokens_transferred': {'0x1234'},
        'interacted_with': {'0xRecv1', '0xRecv2'}
    }
    
    # Now should generate a report
    report = await token_movement_strategy._generate_report()
    assert report is not None
    assert report.title == "Token Movement Daily Report"
    assert report.severity == "info"
    
    # Verify report data
    assert 'total_tokens_tracked' in report.data
    assert 'total_addresses_tracked' in report.data
    assert 'tokens_by_volume' in report.data
    assert 'addresses_by_activity' in report.data
    
    # Check token data
    key = f"{chain_id}:{token_addr}"
    assert key in report.data['tokens_by_volume']
    token_data = report.data['tokens_by_volume'][key]
    assert token_data['token_symbol'] == 'TEST'
    assert token_data['total_volume'] == 1000.0
    
    # Check address data
    addr_key = f"{chain_id}:{token_transfer_event.from_address}"
    assert addr_key in report.data['addresses_by_activity']
    addr_data = report.data['addresses_by_activity'][addr_key]
    assert addr_data['sent_count'] == 5
    assert addr_data['received_count'] == 3 