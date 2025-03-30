import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from sentinel.core.events import TokenTransferEvent
from sentinel.core.alerts import Alert

# Import the refactored strategy
from sentinel.strategies.token_movement.core.strategy import TokenMovementStrategy
from sentinel.strategies.token_movement.detectors.base import BaseDetector
from sentinel.strategies.token_movement.filters.base import BaseFilter

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
        block_timestamp=datetime.now().timestamp(),
        log_index=0,
        is_native=False
    )

@pytest.fixture
def token_movement_strategy():
    """Create a token movement strategy for testing"""
    strategy = TokenMovementStrategy(
        chain_id=1,  # Ethereum
        config={
            'detectors': {
                'significant_transfer': {
                    'significant_transfer_threshold': {
                        'TEST': 50.0,  # Significant threshold for TEST token
                        'ETH': 1.0     # Significant threshold for ETH
                    }
                },
                'watched_address': {
                    'addresses': ['0xWatched1', '0xWatched2']
                },
                'watched_token': {
                    'tokens': ['0x1234567890123456789012345678901234567890']
                }
            },
            'filters': {
                'throttle': {
                    'enabled': True,
                    'cooldown': 0  # No cooldown for easier testing
                }
            }
        }
    )
    return strategy

@pytest.fixture
def mock_detector():
    """Create a mock detector for testing"""
    detector = AsyncMock(spec=BaseDetector)
    detector.is_enabled.return_value = True
    detector.detect.return_value = [
        Alert(
            title="Test Alert",
            description="Test Description",
            severity="medium",
            source="test_detector",
            timestamp=datetime.now(),
            data={"test": "data"}
        )
    ]
    return detector

@pytest.fixture
def mock_filter():
    """Create a mock filter for testing"""
    filter_mock = MagicMock(spec=BaseFilter)
    filter_mock.is_enabled.return_value = True
    filter_mock.should_filter.return_value = False  # Don't filter by default
    return filter_mock

@pytest.mark.asyncio
async def test_strategy_initialization(token_movement_strategy):
    """Test that the strategy initializes correctly with plugins"""
    # Check that detectors and filters are initialized
    assert len(token_movement_strategy.detectors) > 0
    assert len(token_movement_strategy.filters) > 0
    
    # Check that the strategy has the correct configuration
    detector_configs = token_movement_strategy.config.get('detectors', {})
    assert detector_configs.get('significant_transfer', {}).get('significant_transfer_threshold') == {
        'TEST': 50.0,
        'ETH': 1.0
    }
    
    # Check that the watch lists are set correctly
    assert detector_configs.get('watched_address', {}).get('addresses') == ['0xWatched1', '0xWatched2']
    assert detector_configs.get('watched_token', {}).get('tokens') == ['0x1234567890123456789012345678901234567890']

@pytest.mark.asyncio
async def test_watched_address_detection(token_movement_strategy, token_transfer_event):
    """Test that transfers involving watched addresses are detected"""
    # Create a new event with a watched address
    watched_event = TokenTransferEvent(
        chain_id=token_transfer_event.chain_id,
        token_address=token_transfer_event.token_address,
        token_name=token_transfer_event.token_name,
        token_symbol=token_transfer_event.token_symbol,
        token_decimals=token_transfer_event.token_decimals,
        from_address='0xWatched1',  # Watched address
        to_address=token_transfer_event.to_address,
        value=token_transfer_event.value,
        formatted_value=token_transfer_event.formatted_value,
        transaction_hash=token_transfer_event.transaction_hash,
        block_number=token_transfer_event.block_number,
        block_timestamp=token_transfer_event.block_timestamp,
        log_index=token_transfer_event.log_index,
        is_native=token_transfer_event.is_native
    )
    
    # Ensure the detector is properly configured
    detector_configs = token_movement_strategy.config.get('detectors', {})
    addresses = detector_configs.get('watched_address', {}).get('addresses', [])
    assert '0xWatched1' in addresses, "Test setup issue: watched address not in configuration"
    
    # Process the event
    alerts = await token_movement_strategy.analyze_event(watched_event)
    
    # Check that an alert was generated
    assert len(alerts) > 0
    assert any("Watched Address Activity" in alert.title for alert in alerts)

@pytest.mark.asyncio
async def test_watched_token_detection(token_movement_strategy, token_transfer_event):
    """Test that transfers involving watched tokens are detected"""
    # The token in the fixture is already in the watch list
    
    # Ensure the detector is properly configured
    detector_configs = token_movement_strategy.config.get('detectors', {})
    tokens = detector_configs.get('watched_token', {}).get('tokens', [])
    assert token_transfer_event.token_address in tokens, "Test setup issue: watched token not in configuration"
    
    # Process the event
    alerts = await token_movement_strategy.analyze_event(token_transfer_event)
    
    # Check that an alert was generated
    assert len(alerts) > 0
    assert any("Watched Token Activity" in alert.title for alert in alerts)

@pytest.mark.asyncio
async def test_detector_integration(token_movement_strategy, token_transfer_event, mock_detector):
    """Test that detectors are properly integrated and called"""
    # Replace the detectors with our mock
    token_movement_strategy.detectors = {"mock_detector": mock_detector}
    
    # Process the event
    alerts = await token_movement_strategy.analyze_event(token_transfer_event)
    
    # Check that the detector was called
    mock_detector.detect.assert_called_once()
    
    # Check that the alert from the detector was included
    assert len(alerts) > 0
    assert any("Test Alert" in alert.title for alert in alerts)

@pytest.mark.asyncio
async def test_filter_integration(token_movement_strategy, token_transfer_event, mock_filter):
    """Test that filters are properly integrated and called"""
    # Replace the filters with our mock
    token_movement_strategy.filters = {"mock_filter": mock_filter}
    
    # Process the event
    await token_movement_strategy.analyze_event(token_transfer_event)
    
    # Check that the filter was called
    mock_filter.should_filter.assert_called_once()
    
    # Test that when filter returns True, no alerts are generated
    mock_filter.should_filter.return_value = True
    alerts = await token_movement_strategy.analyze_event(token_transfer_event)
    assert len(alerts) == 0

@pytest.mark.asyncio
async def test_statistics_tracking(token_movement_strategy, token_transfer_event):
    """Test that statistics are properly tracked"""
    # Process the event
    await token_movement_strategy.analyze_event(token_transfer_event)
    
    # Check that token statistics were updated
    token_key = token_transfer_event.token_address
    assert token_key in token_movement_strategy.token_stats
    assert token_movement_strategy.token_stats[token_key]['transfer_count'] == 1
    assert token_movement_strategy.token_stats[token_key]['total_volume'] == token_transfer_event.formatted_value
    
    # Check that address statistics were updated
    from_key = token_transfer_event.from_address
    to_key = token_transfer_event.to_address
    
    assert from_key in token_movement_strategy.address_stats
    assert to_key in token_movement_strategy.address_stats
    
    assert token_movement_strategy.address_stats[from_key]['sent_count'] == 1
    assert token_movement_strategy.address_stats[to_key]['received_count'] == 1

@pytest.mark.asyncio
async def test_batch_processing(token_movement_strategy, token_transfer_event):
    """Test that batch processing works correctly"""
    # Create a batch of events
    events = [token_transfer_event] * 3
    
    # Process the batch
    alerts = await token_movement_strategy.process(events)
    
    # Check that alerts were generated for each event
    assert len(alerts) > 0



@pytest.mark.asyncio
async def test_reset_statistics(token_movement_strategy, token_transfer_event):
    """Test that statistics can be reset"""
    # Process an event to have some data
    await token_movement_strategy.analyze_event(token_transfer_event)
    
    # Check that we have data
    assert len(token_movement_strategy.token_stats) > 0
    assert len(token_movement_strategy.address_stats) > 0
    
    # Reset statistics
    token_movement_strategy.reset_statistics()
    
    # Check that data was cleared
    assert len(token_movement_strategy.token_stats) == 0
    assert len(token_movement_strategy.address_stats) == 0
