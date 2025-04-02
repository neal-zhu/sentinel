"""
Core strategy class for the Token Movement Strategy.
"""
import asyncio
import time
import statistics
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

from sentinel.core.base import Strategy
from sentinel.core.events import Event, TokenTransferEvent
from sentinel.core.alerts import Alert
from sentinel.logger import logger

from sentinel.strategies.token_movement.detectors.base import BaseDetector
from sentinel.strategies.token_movement.detectors.significant_transfer import SignificantTransferDetector
from sentinel.strategies.token_movement.detectors.high_frequency import HighFrequencyDetector
from sentinel.strategies.token_movement.detectors.continuous_flow import ContinuousFlowDetector
from sentinel.strategies.token_movement.detectors.periodic_transfer import PeriodicTransferDetector
from sentinel.strategies.token_movement.detectors.multi_hop import MultiHopDetector
from sentinel.strategies.token_movement.detectors.wash_trading import WashTradingDetector

from sentinel.strategies.token_movement.filters.base import BaseFilter
from sentinel.strategies.token_movement.filters.whitelist import WhitelistFilter
from sentinel.strategies.token_movement.filters.small_transfer import SmallTransferFilter
from sentinel.strategies.token_movement.filters.simple_transfer import SimpleTransferFilter
from sentinel.strategies.token_movement.filters.dex_trade import DexTradeFilter

from sentinel.strategies.token_movement.utils.chain_info import ChainInfo
from sentinel.strategies.token_movement.utils.address_utils import AddressUtils
from sentinel.strategies.token_movement.utils.token_utils import TokenUtils

class TokenMovementStrategy(Strategy):
    """
    Token Movement Strategy
    
    Analyzes token transfer events to detect:
    - Large transfers exceeding thresholds
    - Unusual activity patterns (sudden increases in transfer frequency or volume)
    - Specific address activity monitoring
    - Suspicious movement patterns (e.g., multiple hops to obscure destination)
    - Common arbitrage and trading patterns
    
    The strategy maintains statistics on token transfers and can generate alerts
    for unusual or significant activity. It can also generate reports for
    visualization and analysis of token movements over time.
    
    This implementation uses a plugin architecture with detectors and filters
    that can be enabled or disabled as needed.
    """
    
    __component_name__ = "token_movement"
    
    def __init__(
        self,
        # Chain identification
        chain_id: int,
        
        # Core settings
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize Token Movement Strategy for a single blockchain
        
        Args:
            chain_id: ID of the chain this strategy handles
            config: Configuration dictionary with the following structure:
                - 'strategy': Strategy-level configuration
                - 'detectors': Configuration for detector plugins
                - 'filters': Configuration for filter plugins
        """
        super().__init__()
        
        # Set chain information
        self.chain_id = chain_id
        self.chain_name = self._get_chain_name(chain_id)
        
        # Initialize configuration
        self.config = {}
        if config:
            self.config = config
        
        # Initialize statistics tracking
        self.token_stats = {}
        
        # Initialize data structures for tracking transfers and statistics
        self._initialize_data_structures()
        
        # Initialize plugins with configurations
        self._initialize_plugins()
        logger.info(f"TokenMovementStrategy initialized for chain {self.chain_name} (ID: {self.chain_id})")
    

    
    def _initialize_data_structures(self):
        """
        Initialize data structures for tracking transfers and statistics
        """
        # Track token transfers (simplified for single chain)
        self.transfers_by_token: Dict[str, List[TokenTransferEvent]] = defaultdict(list)
        self.transfers_by_address: Dict[str, List[TokenTransferEvent]] = defaultdict(list)
        
        # Track transfer frequencies by block window
        self.network_transfers_by_block: Dict[int, int] = defaultdict(int)
        self.address_transfers_by_block: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        
        # Last alert timestamps to prevent alert spam
        self.last_alert_time: Dict[str, float] = {}
        
        # Statistics (simplified for single chain)
        self.token_stats: Dict[str, Dict[str, Any]] = {}
        self.address_stats: Dict[str, Dict[str, Any]] = {}
        
        # Chain metadata
        self.chain_metadata: Dict[str, Any] = {
            'name': self.chain_name,
            'first_seen': None,
            'last_seen': None,
            'total_volume': 0,
            'transfer_count': 0
        }
        
        # Transaction chains tracking
        self.txn_chains: Dict[str, List[TokenTransferEvent]] = {}
        
        # Known DEX and protocol addresses
        self.known_dexes = AddressUtils.KNOWN_DEXES
        
        # Track last checked block (to avoid duplicate analysis)
        self.last_checked_block: int = 0
        
        # Get alert cooldown from config
        self.alert_cooldown = self.config.get('strategy', {}).get('alert_cooldown', 300)  # Default: 5 minutes
        
        # Initialize caches
        self.token_symbols_cache: Dict[str, str] = {}
        self.token_decimals_cache: Dict[str, int] = {}
        
        # No need to extract config values as instance variables anymore
        # All config values will be accessed directly from self.config when needed
        
    def _get_chain_name(self, chain_id: int) -> str:
        """
        Get chain name from chain ID
        
        Args:
            chain_id: Blockchain chain ID
            
        Returns:
            str: Chain name
        """
        # Map of common chain IDs to their names
        chain_names = {
            1: "ethereum",
            56: "bsc",
            137: "polygon",
            10: "optimism",
            42161: "arbitrum",
            43114: "avalanche",
            250: "fantom"
        }
        return chain_names.get(chain_id, f"chain_{chain_id}")
        
    def _initialize_plugins(self):
        """
        Initialize detector and filter plugins with configurations from self.config.
        This method encapsulates the plugin initialization logic, making the strategy
        more focused on high-level business logic rather than plugin details.
        """
        try:
            # Get detector and filter configurations
            detector_configs = self.config.get('detectors', {})
            filter_configs = self.config.get('filters', {})
            
            # Initialize detector plugins
            self._initialize_detectors(detector_configs)
            
            # Initialize filter plugins
            self._initialize_filters(filter_configs)
            
            logger.info(f"TokenMovementStrategy initialized with {len(self.detectors)} detectors and {len(self.filters)} filters")
        except Exception as e:
            logger.error(f"Error initializing plugins: {e}")
            self.detectors = {}
            self.filters = {}
    
    def _initialize_detectors(self, detector_configs: Dict[str, Dict[str, Any]]):
        """
        Initialize detector plugins with provided configurations.
        Each detector is responsible for handling its own default parameters.
        
        Args:
            detector_configs: Configuration dictionary for detectors
        """
        self.detectors = {}
        
        # Import detector classes
        try:
            # Import all available detector classes
            from sentinel.strategies.token_movement.detectors.significant_transfer import SignificantTransferDetector
            from sentinel.strategies.token_movement.detectors.high_frequency import HighFrequencyDetector
            from sentinel.strategies.token_movement.detectors.continuous_flow import ContinuousFlowDetector
            from sentinel.strategies.token_movement.detectors.periodic_transfer import PeriodicTransferDetector
            from sentinel.strategies.token_movement.detectors.multi_hop import MultiHopDetector
            from sentinel.strategies.token_movement.detectors.wash_trading import WashTradingDetector
            
            # Map detector names to their classes
            detector_classes = {
                'significant_transfer': SignificantTransferDetector,
                'high_frequency': HighFrequencyDetector,
                'continuous_flow': ContinuousFlowDetector,
                'periodic_transfer': PeriodicTransferDetector,
                'multi_hop': MultiHopDetector,
                'wash_trading': WashTradingDetector,
            }
            
            # Initialize all available detectors
            for detector_name, detector_class in detector_classes.items():
                # Get config for this detector if available, otherwise use empty dict
                config = detector_configs.get(detector_name, {})
                
                # Initialize detector - it will handle its own default parameters
                self.detectors[detector_name] = detector_class(config)
                logger.debug(f"Initialized detector: {detector_name}")
                
        except ImportError as e:
            logger.error(f"Error importing detector classes: {e}")
    
    def _initialize_filters(self, filter_configs: Dict[str, Dict[str, Any]]):
        """
        Initialize filter plugins with provided configurations.
        Each filter is responsible for handling its own default parameters.
        
        Args:
            filter_configs: Configuration dictionary for filters
        """
        self.filters = {}
        
        # Import filter classes
        try:
            # Import all available filter classes
            from sentinel.strategies.token_movement.filters.small_transfer import SmallTransferFilter
            from sentinel.strategies.token_movement.filters.whitelist import WhitelistFilter
            from sentinel.strategies.token_movement.filters.simple_transfer import SimpleTransferFilter
            from sentinel.strategies.token_movement.filters.dex_trade import DexTradeFilter
            
            # Map filter names to their classes
            filter_classes = {
                'small_transfer': SmallTransferFilter,
                'whitelist': WhitelistFilter,
                'simple_transfer': SimpleTransferFilter,
                'dex_trade': DexTradeFilter,
            }
            
            # Initialize all available filters
            for filter_name, filter_class in filter_classes.items():
                # Get config for this filter if available, otherwise use empty dict
                config = filter_configs.get(filter_name, {})
                
                # Initialize filter - it will handle its own default parameters
                self.filters[filter_name] = filter_class(config)
                logger.debug(f"Initialized filter: {filter_name}")
                
        except ImportError as e:
            logger.error(f"Error importing filter classes: {e}")
            
            logger.info(f"TokenMovementStrategy initialized with {len(self.detectors)} detectors and {len(self.filters)} filters")
        except Exception as e:
            logger.error(f"Error initializing plugins: {e}")
            self.detectors = {}
            self.filters = {}
    

        
    def _update_statistics(self, event: TokenTransferEvent):
        """
        Update statistical tracking for tokens and addresses
        
        Args:
            event: Token transfer event
        """
        # Verify event is from the correct chain
        if event.chain_id != self.chain_id:
            logger.warning(f"Received event from chain {event.chain_id}, but this strategy handles chain {self.chain_id}")
            return
            
        # Update chain metadata
        if self.chain_metadata['first_seen'] is None:
            self.chain_metadata['first_seen'] = event.block_timestamp
            
        self.chain_metadata['last_seen'] = event.block_timestamp
        self.chain_metadata['transfer_count'] += 1
        self.chain_metadata['total_volume'] += event.formatted_value
        
        # Store event by token
        token_key = event.token_address or 'native'
        token_events = self.transfers_by_token[token_key]
        
        # Add new event
        token_events.append(event)
        
        # Get anomaly window size from config or use default
        anomaly_window_size = self.config.get('detectors', {}).get('high_frequency', {}).get('window_size', 100)
        
        # Limit size of history to control memory usage
        max_events = max(1000, anomaly_window_size * 3)
        if len(token_events) > max_events:
            self.transfers_by_token[token_key] = token_events[-max_events:]
        
        # Update token statistics
        if token_key not in self.token_stats:
            self.token_stats[token_key] = {
                'first_seen': event.block_timestamp,
                'last_seen': event.block_timestamp,
                'total_volume': event.formatted_value,
                'transfer_count': 1,
                'avg_transfer': event.formatted_value,
                'max_transfer': event.formatted_value,
                'min_transfer': event.formatted_value,
                'mean_value': event.formatted_value,
                'stdev_value': 0,
                'token_symbol': event.token_symbol,
                'token_name': event.token_name,
                'token_address': event.token_address,
                'is_native': event.is_native
            }
        else:
            # Update existing stats
            stats = self.token_stats[token_key]
            stats['last_seen'] = event.block_timestamp
            stats['total_volume'] += event.formatted_value
            stats['transfer_count'] += 1
            stats['max_transfer'] = max(stats['max_transfer'], event.formatted_value)
            stats['min_transfer'] = min(stats['min_transfer'], event.formatted_value)
            stats['avg_transfer'] = stats['total_volume'] / stats['transfer_count']
            
            # Get anomaly window size from config or use default
            anomaly_window_size = self.config.get('detectors', {}).get('high_frequency', {}).get('window_size', 100)
            
            # Calculate running statistics
            recent_transfers = self.transfers_by_token[token_key][-anomaly_window_size:]
            if len(recent_transfers) >= 2:  # Need at least 2 values for standard deviation
                values = [t.formatted_value for t in recent_transfers]
                try:
                    stats['mean_value'] = statistics.mean(values)
                    stats['stdev_value'] = statistics.stdev(values)
                except statistics.StatisticsError:
                    # Handle error if values are all the same
                    stats['mean_value'] = values[0] if values else 0
                    stats['stdev_value'] = 0
        
        # Store event by address
        for address in [event.from_address, event.to_address]:
            address_events = self.transfers_by_address[address]
            
            # Add new event
            address_events.append(event)
            
            # Limit size of history
            if len(address_events) > max_events:
                self.transfers_by_address[address] = address_events[-max_events:]
            
            # Update address statistics
            is_sender = address == event.from_address
            
            if address not in self.address_stats:
                self.address_stats[address] = {
                    'first_seen': event.block_timestamp,
                    'last_seen': event.block_timestamp,
                    'last_active': event.block_timestamp,
                    'sent_count': 1 if is_sender else 0,
                    'received_count': 0 if is_sender else 1,
                    'total_sent': event.formatted_value if is_sender else 0,
                    'total_received': 0 if is_sender else event.formatted_value,
                    'tokens_transferred': {event.token_address or 'native'},
                    'interacted_with': {event.to_address if is_sender else event.from_address}
                }
            else:
                # Update existing stats
                stats = self.address_stats[address]
                stats['last_seen'] = event.block_timestamp
                stats['last_active'] = event.block_timestamp
                
                if is_sender:
                    stats['sent_count'] += 1
                    stats['total_sent'] += event.formatted_value
                    stats['interacted_with'].add(event.to_address)
                else:
                    stats['received_count'] += 1
                    stats['total_received'] += event.formatted_value
                    stats['interacted_with'].add(event.from_address)
                    
                stats['tokens_transferred'].add(event.token_address or 'native')
        
        # Update transfer frequency tracking
        block_number = event.block_number
        
        # Update network-wide frequency
        self.network_transfers_by_block[block_number] += 1
        
        # Update address-specific frequency
        self.address_transfers_by_block[event.from_address][block_number] += 1
        
        # Update last checked block
        self.last_checked_block = max(self.last_checked_block, event.block_number)
    
    def _should_alert(self, alert_key: str) -> bool:
        """
        Check if we should send an alert based on cooldown time
        
        Args:
            alert_key: Unique identifier for this type of alert
            
        Returns:
            bool: Whether to send the alert
        """
        current_time = time.time()
        last_alert_time = self.last_alert_time.get(alert_key, 0)
        
        # Check if we're past the cooldown period
        if current_time - last_alert_time > self.alert_cooldown:
            # Update last alert time
            self.last_alert_time[alert_key] = current_time
            return True
            
        # Still in cooldown
        return False
    
    def _deduplicate_alerts(self, alerts: List[Alert]) -> List[Alert]:
        """
        Deduplicate and rate limit alerts to prevent alert fatigue
        
        Args:
            alerts: List of alerts to process
            
        Returns:
            List[Alert]: Deduplicated alerts
        """
        if not alerts:
            return []
            
        # Track alert signatures to prevent duplicates in same batch
        seen_signatures = set()
        deduplicated = []
        duplicates_count = 0
        
        for alert in alerts:
            # Create a unique signature for this alert
            if hasattr(alert.data, 'get'):
                signature = f"{alert.title}:{alert.data.get('chain_id')}:{alert.data.get('from_address')}:{alert.data.get('transaction_hash')}"
            else:
                # Fallback if data is not a dict-like object
                signature = f"{alert.title}:{alert.source}:{alert.severity}"
                
            # Skip if we've already seen this alert signature
            if signature in seen_signatures:
                duplicates_count += 1
                continue
                
            seen_signatures.add(signature)
            deduplicated.append(alert)
        
        if duplicates_count > 0:
            logger.debug(f"Removed {duplicates_count} duplicate alerts")
            
        # Record final alert types and counts
        if deduplicated:
            alert_types_count = {}
            for alert in deduplicated:
                alert_types_count[alert.title] = alert_types_count.get(alert.title, 0) + 1
                
            logger.debug(f"Alert types after deduplication: {alert_types_count}")
        
        return deduplicated
    
    async def _prepare_event(self, event: TokenTransferEvent) -> TokenTransferEvent:
        """
        Prepare an event for processing by ensuring all required fields are populated
        
        Args:
            event: The token transfer event to prepare
            
        Returns:
            TokenTransferEvent: The prepared event
        """
        # Create a working copy of the event for modification
        modified_event = event
        needs_model_copy = False
        
        # Check if we need to initialize token symbol
        token_symbol = event.token_symbol if hasattr(event, 'token_symbol') else None
        if not token_symbol:
            needs_model_copy = True
            token_symbol = TokenUtils.get_token_symbol(
                event.chain_id, 
                event.token_address or '', 
                self.token_symbols_cache
            )
            logger.debug(f"Initialized token symbol: {token_symbol}")
            
        # Check if we need to initialize formatted value
        formatted_value = event.formatted_value if hasattr(event, 'formatted_value') else None
        if not formatted_value:
            needs_model_copy = True
            formatted_value = TokenUtils.format_token_value(
                event.chain_id, 
                event.token_address or '', 
                event.value,
                self.token_decimals_cache
            )
            logger.debug(f"Initialized formatted value: {formatted_value}")
        
        # If we need to modify, create a copy of the model and update fields
        if needs_model_copy:
            try:
                # Use model_copy method to create a modifiable copy (Pydantic v2 syntax)
                modified_event = event.model_copy(update={
                    "token_symbol": token_symbol or event.token_symbol,
                    "formatted_value": formatted_value or event.formatted_value
                })
                logger.debug("Created modified event using model_copy")
            except AttributeError:
                # If using Pydantic v1, use copy method
                try:
                    modified_event = event.copy(update={
                        "token_symbol": token_symbol or event.token_symbol,
                        "formatted_value": formatted_value or event.formatted_value
                    })
                    logger.debug("Created modified event using copy")
                except AttributeError:
                    # If both methods fail, log error and continue with original event
                    logger.error(f"Unable to update event fields due to Pydantic model restrictions")
                    
        return modified_event
    
    async def process_event(self, event: Event) -> List[Any]:
        """
        Process an incoming event and generate alerts if applicable.
        This is the main entry point for the strategy.
        
        Args:
            event: The event to process
            
        Returns:
            List[Any]: Alerts generated from this event
        """
        # We only care about token transfer events
        if not isinstance(event, TokenTransferEvent):
            return []
        
        # Prepare the event for processing
        modified_event = await self._prepare_event(event)
        
        # Log basic event information
        logger.debug(f"Processing token transfer: chain={modified_event.chain_id}, tx={modified_event.transaction_hash}, from={modified_event.from_address}, to={modified_event.to_address}")
        
        # Analyze the event and generate alerts
        alerts = await self.analyze_event(modified_event)
        
        if alerts:
            logger.info(f"Generated {len(alerts)} alerts for token transfer: chain={modified_event.chain_id}, tx={modified_event.transaction_hash}, value={modified_event.formatted_value} {modified_event.token_symbol}")
        
        return alerts
    
    async def analyze_event(self, event: TokenTransferEvent) -> List[Alert]:
        """
        Main entry point for analyzing a token transfer event.
        This method coordinates all detection mechanisms and aggregates alerts.
        
        Args:
            event: The token transfer event to analyze
            
        Returns:
            List[Alert]: A list of alerts generated from this event
        """
        # Verify event is from the correct chain
        if event.chain_id != self.chain_id:
            logger.warning(f"Received event from chain {event.chain_id}, but this strategy handles chain {self.chain_id}")
            return []
            
        # Get configuration values from config
        detector_configs = self.config.get('detectors', {})
        filter_configs = self.config.get('filters', {})
        
        # Get watched addresses and tokens from config
        watched_addresses = detector_configs.get('watched_address', {}).get('addresses', [])
        watched_tokens = detector_configs.get('watched_token', {}).get('tokens', [])
        whitelist_addresses = filter_configs.get('whitelist', {}).get('whitelist_addresses', [])
        
        # Create context dictionary to share information between components
        context = {
            'token_stats': self.token_stats,
            'address_stats': self.address_stats,
            'transfers_by_token': self.transfers_by_token,
            'transfers_by_address': self.transfers_by_address,
            'address_transfers_by_block': self.address_transfers_by_block,
            'network_transfers_by_block': self.network_transfers_by_block,
            'last_checked_block': self.last_checked_block,
            'known_dexes': self.known_dexes,
            'whitelist_addresses': whitelist_addresses,
            'is_watched_from': event.from_address in watched_addresses,
            'is_watched_to': event.to_address in watched_addresses,
            'is_watched_token': False,  # Will be set below if applicable
            'is_high_interest_token': False,  # Will be set in the filter check
        }
        
        # Check if this is a watched token
        if event.token_address:
            context['is_watched_token'] = event.token_address in watched_tokens
        
        # Apply filters to determine if we should process this event
        should_filter = False
        for filter_name, filter_plugin in self.filters.items():
            if filter_plugin.is_enabled() and filter_plugin.should_filter(event, context):
                logger.debug(f"Event filtered by {filter_name}: {event.transaction_hash}")
                should_filter = True
                break
                
        # Skip if this event should be filtered
        if should_filter:
            return []
            
        # Track the transfer in our statistics
        self._update_statistics(event)
        
        # Collect alerts from all enabled detectors
        all_alerts = []
        
        # Special handling for watched addresses/tokens - generate alerts with appropriate context
        is_watched_from = context['is_watched_from']
        is_watched_to = context['is_watched_to']
        is_watched_token = context['is_watched_token']
        is_high_interest_token = context.get('is_high_interest_token', False)
        is_dex_trade = context.get('is_dex_trade', False)
        is_significant_transfer = context.get('is_significant_transfer', False)
        
        # Only alert on watched addresses/tokens if they are part of a significant transfer or DEX trade
        # This helps reduce noise from routine transfers
        should_alert_watched = (is_watched_from or is_watched_to or is_watched_token) and (
            is_significant_transfer or is_dex_trade or is_high_interest_token
        )
        
        if should_alert_watched:
            watch_type = []
            if is_watched_from or is_watched_to:
                watch_type.append("address")
            if is_watched_token:
                watch_type.append("token")
            
            watched_items = []
            if is_watched_from:
                watched_items.append(f"from:{event.from_address}")
            if is_watched_to:
                watched_items.append(f"to:{event.to_address}")
            if is_watched_token:
                watched_items.append(f"token:{event.token_address}")
                
            alert_context = []
            if is_significant_transfer:
                alert_context.append("significant transfer")
            if is_dex_trade:
                alert_context.append("DEX trade")
            if is_high_interest_token:
                alert_context.append("high interest token")
                
            alert_title = f"Watched {', '.join(watch_type)} Activity: {', '.join(alert_context)}"
            
            logger.info(f"Transfer involving watched {'/'.join(watch_type)} detected: {', '.join(watched_items)}")
            
            all_alerts.append(Alert(
                title=alert_title,
                description=f"Transfer involving watched {'/'.join(watch_type)} {', '.join(watched_items)}",
                severity="medium",
                source="token_movement_strategy",
                timestamp=datetime.now(),
                data={
                    "chain_id": self.chain_id,
                    "chain_name": self.chain_name,
                    "token_symbol": event.token_symbol,
                    "token_address": event.token_address,
                    "from_address": event.from_address,
                    "to_address": event.to_address,
                    "from_watched": is_watched_from,
                    "to_watched": is_watched_to,
                    "token_watched": is_watched_token,
                    "high_interest_token": is_high_interest_token, 
                    "is_dex_trade": is_dex_trade,
                    "is_significant": is_significant_transfer,
                    "value": str(event.value),
                    "formatted_value": event.formatted_value,
                    "transaction_hash": event.transaction_hash,
                    "block_number": event.block_number
                }
            ))
        
        # Run each enabled detector against the event
        for detector_name, detector in self.detectors.items():
            if detector.is_enabled():
                try:
                    detector_alerts = await detector.detect(event, context)
                    
                    # Check if we should rate-limit alerts from this detector
                    if detector_alerts:
                        for alert in detector_alerts:
                            # Create a unique key for each type of alert
                            alert_key = f"{detector_name}:{event.chain_id}:{event.token_address or 'native'}"
                            
                            # Add specific identifier for the alert if available
                            if hasattr(alert, 'data') and alert.data and 'pattern_type' in alert.data:
                                alert_key += f":{alert.data['pattern_type']}"
                                
                            # Check if we should send this alert (rate limiting)
                            if self._should_alert(alert_key):
                                all_alerts.append(alert)
                            else:
                                logger.debug(f"Alert from {detector_name} rate-limited: {alert_key}")
                                
                except Exception as e:
                    logger.error(f"Error in detector {detector_name}: {e}")
        
        return all_alerts
    
    async def process(self, events: List[Event]) -> List[Any]:
        """
        Process a batch of events and generate alerts according to the token movement strategy.
        
        Args:
            events: List of events to process
            
        Returns:
            List[Any]: List of alerts or actions generated
        """
        all_alerts = []
        token_transfer_count = 0
        
        # Log processing start
        logger.debug(f"TokenMovementStrategy.process: Processing batch of {len(events)} events")
        
        # Process each event
        for event in events:
            # Only process token transfer events
            if isinstance(event, TokenTransferEvent):
                token_transfer_count += 1
                alerts = await self.process_event(event)
                if alerts:
                    logger.debug(f"Generated {len(alerts)} alerts for event {event.transaction_hash}")
                all_alerts.extend(alerts)
        
        # Log processing results
        if all_alerts:
            logger.info(f"TokenMovementStrategy.process: Processed {token_transfer_count}/{len(events)} token transfers, generated {len(all_alerts)} alerts/actions")
        else:
            logger.debug(f"TokenMovementStrategy.process: Processed {token_transfer_count}/{len(events)} token transfers, no alerts generated")
            
        return all_alerts
    

    
    def reset_statistics(self):
        """
        Reset all statistical tracking data
        """
        logger.info("Resetting token movement statistics")
        
        self.transfers_by_token = defaultdict(list)
        self.transfers_by_address = defaultdict(list)
        self.token_stats = {}
        self.address_stats = {}
        
        # Reset chain metadata but keep chain identification
        self.chain_metadata = {
            'name': self.chain_name,
            'first_seen': None,
            'last_seen': None,
            'total_volume': 0,
            'transfer_count': 0
        }
        
        self.network_transfers_by_block = defaultdict(int)
        self.address_transfers_by_block = defaultdict(lambda: defaultdict(int))
        self.last_alert_time = {}
        self.last_checked_block = 0
