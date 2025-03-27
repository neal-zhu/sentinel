import asyncio
import time
import math
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

from sentinel.core.base import Strategy
from sentinel.core.events import Event, TokenTransferEvent
from sentinel.core.alerts import Alert
from sentinel.logger import logger

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
    """
    
    __component_name__ = "token_movement"
    
    # Average block times for different chains (in seconds)
    # Used for estimating time windows from block numbers
    BLOCK_TIMES = {
        1: 15,    # Ethereum: ~15 seconds
        56: 3,    # BSC: ~3 seconds
        137: 2,    # Polygon: ~2 seconds
        10: 2,     # Optimism: ~2 seconds
        42161: 0.25,  # Arbitrum: ~0.25 seconds
        43114: 2,  # Avalanche: ~2 seconds
        250: 1,    # Fantom: ~1 second
        25: 6,     # Cronos: ~6 seconds
        100: 5,    # Gnosis Chain: ~5 seconds
        # More chains can be added as needed
    }
    
    # Default block time for chains not in the list
    DEFAULT_BLOCK_TIME = 15  # seconds
    
    def __init__(
        self,
        # Alert thresholds
        significant_transfer_threshold: Optional[Dict[str, Dict[str, float]]] = None,  # Thresholds by chain and token
        unusual_volume_threshold: float = 3.0,  # Multiple of standard deviation to consider unusual
        unusual_frequency_threshold: float = 3.0,  # Multiple of standard deviation to consider unusual
        anomaly_window_size: int = 100,  # Number of transfers to use for anomaly detection baseline
        
        # Monitoring settings
        watch_addresses: Optional[Dict[str, List[str]]] = None,  # Addresses to watch closely, by chain
        watch_tokens: Optional[Dict[str, List[str]]] = None,  # Tokens to watch closely, by chain
        blacklist_addresses: Optional[Dict[str, List[str]]] = None,  # Known suspicious addresses, by chain
        
        # Alert settings
        alert_cooldown: int = 300,  # Seconds to wait before sending similar alerts
        throttle_alerts: bool = True,  # Whether to throttle alerts
        
        # Reporting settings
        daily_report: bool = True,  # Whether to generate daily reports
        statistics_window: int = 24,  # Hours to consider for statistics in reports
        
        # NEW: Noise reduction settings
        whitelist_addresses: Optional[Dict[str, List[str]]] = None,  # Known good addresses to ignore (DEXs, etc)
        filter_small_transfers: bool = True,  # Whether to filter out small transfers
        relative_size_threshold: float = 0.05,  # Percentage of token market cap to consider significant
        
        # NEW: Arbitrage detection settings
        detect_arbitrage: bool = True,  # Whether to detect arbitrage patterns
        arbitrage_time_window: int = 60,  # Seconds to consider for arbitrage detection
        flash_loan_detection: bool = True,  # Whether to detect flash loans
        triangle_pattern_detection: bool = True,  # Whether to detect triangle arbitrage
        
        # NEW: Advanced pattern detection
        track_txn_chains: bool = True,  # Whether to track transaction chains 
        max_chain_depth: int = 5,  # Maximum depth of transaction chains to track
        track_liquidity_events: bool = True,  # Whether to track liquidity addition/removal
    ):
        """
        Initialize Token Movement Strategy
        
        Args:
            significant_transfer_threshold: Thresholds for significant transfers, by chain and token
                Format: {'ethereum': {'ETH': 100.0, 'USDT': 100000.0}, 'bsc': {'BNB': 500.0}}
            unusual_volume_threshold: How many standard deviations above mean to consider unusual volume
            unusual_frequency_threshold: How many standard deviations above mean to consider unusual frequency
            anomaly_window_size: Number of transfers to consider for baseline stats
            watch_addresses: Addresses to monitor closely, by chain
            watch_tokens: Token contracts to monitor closely, by chain
            blacklist_addresses: Known suspicious addresses, by chain
            alert_cooldown: Seconds to wait before sending similar alerts
            throttle_alerts: Whether to throttle similar alerts
            daily_report: Whether to generate daily statistics reports
            statistics_window: Hours of data to include in statistics
            whitelist_addresses: Known good addresses to ignore (DEXs, exchanges, etc)
            filter_small_transfers: Whether to filter out small transfers
            relative_size_threshold: Percentage of token market cap to consider significant
            detect_arbitrage: Whether to detect arbitrage patterns
            arbitrage_time_window: Seconds to consider for arbitrage detection
            flash_loan_detection: Whether to detect flash loans
            triangle_pattern_detection: Whether to detect triangle arbitrage
            track_txn_chains: Whether to track transaction chains
            max_chain_depth: Maximum depth of transaction chains to track
            track_liquidity_events: Whether to track liquidity addition/removal
        """
        super().__init__()
        
        # Initialize parameters
        self.significant_transfer_threshold = significant_transfer_threshold or {}
        self.unusual_volume_threshold = unusual_volume_threshold
        self.unusual_frequency_threshold = unusual_frequency_threshold
        self.anomaly_window_size = anomaly_window_size
        self.watch_addresses = watch_addresses or {}
        self.watch_tokens = watch_tokens or {}
        self.blacklist_addresses = blacklist_addresses or {}
        self.alert_cooldown = alert_cooldown
        self.throttle_alerts = throttle_alerts
        self.daily_report = daily_report
        self.statistics_window = statistics_window
        
        # NEW: Initialize noise reduction parameters
        self.whitelist_addresses = whitelist_addresses or {}
        self.filter_small_transfers = filter_small_transfers
        self.relative_size_threshold = relative_size_threshold
        
        # NEW: Initialize arbitrage detection parameters
        self.detect_arbitrage = detect_arbitrage
        self.arbitrage_time_window = arbitrage_time_window
        self.flash_loan_detection = flash_loan_detection
        self.triangle_pattern_detection = triangle_pattern_detection
        
        # NEW: Initialize advanced pattern detection
        self.track_txn_chains = track_txn_chains
        self.max_chain_depth = max_chain_depth
        self.track_liquidity_events = track_liquidity_events
        
        # Track token transfers
        self.transfers_by_token: Dict[Tuple[int, str], List[TokenTransferEvent]] = defaultdict(list)
        self.transfers_by_address: Dict[Tuple[int, str], List[TokenTransferEvent]] = defaultdict(list)
        
        # Track transfer frequencies by block window
        self.network_transfers_by_block: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self.address_transfers_by_block: Dict[Tuple[int, str], Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        
        # Last alert timestamps to prevent alert spam
        self.last_alert_time: Dict[str, float] = {}
        
        # Statistics
        self.token_stats: Dict[Tuple[int, str], Dict[str, Any]] = {}
        self.address_stats: Dict[Tuple[int, str], Dict[str, Any]] = {}
        
        # Chain metadata
        self.chain_metadata: Dict[int, Dict[str, Any]] = {}
        
        # NEW: Transaction chains tracking
        self.txn_chains: Dict[str, List[TokenTransferEvent]] = {}
        
        # NEW: Common DEX and protocol addresses
        self.known_dexes: Dict[int, List[str]] = self._initialize_known_dexes()
        
        # Track last checked blocks (to avoid duplicate analysis)
        self.last_checked_block: Dict[int, int] = {}
        
        # Initialize reporting
        self.last_report_time = datetime.now()
        
        # Initialize caches
        self.token_symbols_cache: Dict[str, str] = {}
        self.token_decimals_cache: Dict[str, int] = {}
        
        # Additional parameters
        self.significant_threshold = 100.0  # Default value for significant net flow
        
        # 记录策略初始化
        logger.info(f"TokenMovementStrategy initialized with {len(self.known_dexes)} known DEX chains")
    
    def _initialize_known_dexes(self) -> Dict[int, List[str]]:
        """Initialize known DEX addresses for major chains"""
        # Common DEX and protocol addresses by chain
        # These are addresses that generate a lot of normal transaction noise
        return {
            1: [  # Ethereum
                "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",  # Uniswap V2 Router
                "0xe592427a0aece92de3edee1f18e0157c05861564",  # Uniswap V3 Router
                "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f",  # SushiSwap Router
                "0x1111111254fb6c44bac0bed2854e76f90643097d",  # 1inch Router
                "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9",  # Aave v2
                "0x398ec7346dcd622edc5ae82352f02be94c62d119",  # Aave v1
                "0x3d9819210a31b4961b30ef54be2aed79b9c9cd3b",  # Compound
            ],
            56: [  # Binance Smart Chain
                "0x10ed43c718714eb63d5aa57b78b54704e256024e",  # PancakeSwap Router v2
                "0x05ff2b0db69458a0750badebc4f9e13add608c7f",  # PancakeSwap Router v1
                "0x1111111254fb6c44bac0bed2854e76f90643097d",  # 1inch Router
            ],
            137: [  # Polygon
                "0xa5e0829caced8ffdd4de3c43696c57f7d7a678ff",  # QuickSwap Router
                "0x1111111254fb6c44bac0bed2854e76f90643097d",  # 1inch Router
                "0x8954afa98594b838bda56fe4c12a09d7739d179b",  # Sushi Router
            ],
            42161: [  # Arbitrum
                "0x1111111254fb6c44bac0bed2854e76f90643097d",  # 1inch Router
                "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f",  # SushiSwap Router
            ],
            10: [  # Optimism
                "0x1111111254fb6c44bac0bed2854e76f90643097d",  # 1inch Router
                "0xe592427a0aece92de3edee1f18e0157c05861564",  # Uniswap V3 Router
            ],
        }
    
    def _estimate_time_from_blocks(self, chain_id: int, block_diff: int) -> int:
        """
        Estimate time in seconds based on block difference
        
        Args:
            chain_id: Blockchain ID
            block_diff: Number of blocks
            
        Returns:
            int: Estimated time in seconds
        """
        block_time = self.BLOCK_TIMES.get(chain_id, self.DEFAULT_BLOCK_TIME)
        return int(block_diff * block_time)
    
    def _estimate_blocks_from_time(self, chain_id: int, seconds: int) -> int:
        """
        Estimate number of blocks based on time in seconds
        
        Args:
            chain_id: Blockchain ID
            seconds: Time in seconds
            
        Returns:
            int: Estimated number of blocks
        """
        block_time = self.BLOCK_TIMES.get(chain_id, self.DEFAULT_BLOCK_TIME)
        return max(1, int(seconds / block_time))
    
    def _get_chain_name(self, chain_id: int) -> str:
        """
        Get human-readable chain name for a chain ID
        
        Args:
            chain_id: Blockchain ID
            
        Returns:
            str: Human-readable chain name
        """
        # Common chain IDs
        chains = {
            1: "Ethereum",
            56: "Binance Smart Chain",
            137: "Polygon",
            10: "Optimism",
            42161: "Arbitrum",
            43114: "Avalanche",
            250: "Fantom",
            25: "Cronos",
            100: "Gnosis Chain",
            42220: "Celo",
            1313161554: "Aurora",
            8217: "Klaytn",
            1284: "Moonbeam",
            1285: "Moonriver",
            128: "Huobi ECO Chain"
        }
        
        return chains.get(chain_id, f"Chain {chain_id}")
    
    def _detect_wash_trading(self, event: TokenTransferEvent) -> bool:
        """
        Detect potential wash trading patterns
        
        Args:
            event: Token transfer event
            
        Returns:
            bool: Whether potential wash trading was detected
        """
        # Check for transfers back and forth between the same addresses
        from_key = (event.chain_id, event.from_address)
        to_key = (event.chain_id, event.to_address)
        
        # Get recent transfers from both addresses
        from_transfers = self.transfers_by_address.get(from_key, [])
        to_transfers = self.transfers_by_address.get(to_key, [])
        
        # Look at recent transfers (last 24 hours)
        recent_time = event.block_timestamp - timedelta(hours=24)
        
        # Count transfers between these two addresses
        back_and_forth = 0
        
        for t in from_transfers:
            if t.block_timestamp >= recent_time and t.to_address == event.to_address:
                back_and_forth += 1
                
        for t in to_transfers:
            if t.block_timestamp >= recent_time and t.to_address == event.from_address:
                back_and_forth += 1
                
        # If we've seen multiple transfers back and forth, this could be wash trading
        return back_and_forth >= 3
    
    def _calculate_price_impact(self, event: TokenTransferEvent) -> Optional[float]:
        """
        Calculate potential price impact of a transfer
        
        Args:
            event: Token transfer event
            
        Returns:
            Optional[float]: Estimated price impact percentage
        """
        # This is a simplified model and would need to be adapted for your specific use case
        # A real implementation would use liquidity data from DEXs
        
        token_key = (event.chain_id, event.token_address or 'native')
        if token_key not in self.token_stats:
            return None
            
        stats = self.token_stats[token_key]
        
        # If we have average transfer size, we can estimate impact
        if 'avg_transfer' in stats and stats['avg_transfer'] > 0:
            avg_size = stats['avg_transfer']
            # Very simplistic model: impact scales with transfer size relative to average
            impact = (event.formatted_value / avg_size) * 0.01  # 1% impact per avg transfer size
            # Cap at reasonable value
            return min(impact, 0.5)  # Max 50% impact
            
        return None
    
    def _update_statistics(self, event: TokenTransferEvent):
        """
        Update statistical tracking for tokens and addresses
        
        Args:
            event: Token transfer event
        """
        # Initialize chain metadata if needed
        if event.chain_id not in self.chain_metadata:
            self.chain_metadata[event.chain_id] = {
                'name': self._get_chain_name(event.chain_id),
                'first_seen': event.block_timestamp,
                'last_seen': event.block_timestamp,
                'total_volume': 0,
                'transfer_count': 0
            }
        else:
            # Update chain stats
            metadata = self.chain_metadata[event.chain_id]
            metadata['last_seen'] = event.block_timestamp
            metadata['transfer_count'] += 1
            metadata['total_volume'] += event.formatted_value
        
        # Store event by token
        token_key = (event.chain_id, event.token_address or 'native')
        token_events = self.transfers_by_token[token_key]
        
        # Add new event
        token_events.append(event)
        
        # Limit size of history to control memory usage
        max_events = max(1000, self.anomaly_window_size * 3)
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
            
            # Calculate running statistics
            recent_transfers = self.transfers_by_token[token_key][-self.anomaly_window_size:]
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
            address_key = (event.chain_id, address)
            address_events = self.transfers_by_address[address_key]
            
            # Add new event
            address_events.append(event)
            
            # Limit size of history
            if len(address_events) > max_events:
                self.transfers_by_address[address_key] = address_events[-max_events:]
            
            # Update address statistics
            is_sender = address == event.from_address
            
            if address_key not in self.address_stats:
                self.address_stats[address_key] = {
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
                stats = self.address_stats[address_key]
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
    
    async def _check_for_unusual_patterns(self, event: TokenTransferEvent) -> List[Alert]:
        """
        Check for unusual patterns in token transfers
        
        Args:
            event: Token transfer event
            
        Returns:
            List[Alert]: Alerts generated
        """
        alerts = []
        
        # Skip pattern detection if this is a likely DEX trade or whitelisted address
        if self._is_likely_dex_trade(event) and not self._is_significant_transfer(event):
            logger.debug(f"Skipping unusual pattern detection for likely DEX trade: tx={event.transaction_hash}")
            return []
            
        # Skip if this should be filtered based on other criteria
        if self._should_filter_transfer(event):
            logger.debug(f"Skipping unusual pattern detection for filtered transfer: tx={event.transaction_hash}")
            return []
        
        # Get chain info for alert context
        chain_name = self._get_chain_name(event.chain_id)
        
        # 1. Check for blacklisted addresses
        if hasattr(self, 'blacklist_addresses'):
            from_blacklisted = self._is_blacklisted_address(event.chain_id, event.from_address)
            to_blacklisted = self._is_blacklisted_address(event.chain_id, event.to_address)
            
            if from_blacklisted or to_blacklisted:
                blacklisted_addresses = []
                if from_blacklisted:
                    blacklisted_addresses.append(event.from_address)
                if to_blacklisted:
                    blacklisted_addresses.append(event.to_address)
                    
                logger.warning(f"Transfer involving blacklisted address detected: {', '.join(blacklisted_addresses)}")
                    
                alert_key = f"blacklist:{event.chain_id}:{event.from_address}:{event.to_address}"
                    
                if self._should_alert(alert_key):
                    alerts.append(Alert(
                        title="Blacklisted Address Activity",
                        description=f"Transfer involving blacklisted address(es): {', '.join(blacklisted_addresses)}",
                        severity="high",
                        source="token_movement_strategy",
                        timestamp=datetime.now(),  # Use current time instead of block timestamp
                        data={
                            "chain_id": event.chain_id,
                            "chain_name": chain_name,
                            "token_symbol": event.token_symbol,
                            "token_address": event.token_address,
                            "from_address": event.from_address,
                            "to_address": event.to_address,
                            "value": str(event.value),
                            "formatted_value": event.formatted_value,
                            "transaction_hash": event.transaction_hash,
                            "block_number": event.block_number,
                            "blacklisted_addresses": blacklisted_addresses
                        }
                    ))
        
        # 2. Check for unusual transfers based on historical data
        # Only do this for non-DEX transfers to reduce noise
        if self._is_unusual_transfer(event) and not self._is_likely_dex_trade(event):
            token_key = (event.chain_id, event.token_address or 'native')
            stats = self.token_stats.get(token_key, {})
            mean_value = stats.get('mean_value', 0)
            stdev_value = stats.get('stdev_value', 0)
            
            # Calculate how unusual this transfer is
            z_score = 0
            if stdev_value > 0:
                z_score = (event.formatted_value - mean_value) / stdev_value
                magnitude = f"{z_score:.2f} standard deviations from mean"
                logger.info(f"Unusual transfer detected: {event.formatted_value} {event.token_symbol or 'native'} (z-score={z_score:.2f})")
            else:
                magnitude = f"{event.formatted_value / mean_value:.2f}x average transfer size" if mean_value > 0 else "significantly large"
                logger.info(f"Unusual transfer detected: {event.formatted_value} {event.token_symbol or 'native'} ({magnitude})")
            
            alert_key = f"unusual:{event.chain_id}:{event.token_symbol or 'native'}"
            
            if self._should_alert(alert_key):
                # Only alert for truly unusual transfers (higher z-score)
                if stdev_value == 0 or z_score > self.unusual_volume_threshold:
                    alerts.append(Alert(
                        title="Unusual Token Transfer",
                        description=f"Transfer of {event.formatted_value} {event.token_symbol or 'native tokens'} is {magnitude}",
                        severity="medium",
                        source="token_movement_strategy",
                        timestamp=datetime.now(),  # Use current time
                        data={
                            "chain_id": event.chain_id,
                            "chain_name": chain_name,
                            "token_symbol": event.token_symbol,
                            "token_address": event.token_address,
                            "from_address": event.from_address,
                            "to_address": event.to_address,
                            "value": str(event.value),
                            "formatted_value": event.formatted_value,
                            "transaction_hash": event.transaction_hash,
                            "mean_value": mean_value,
                            "stdev_value": stdev_value,
                            "magnitude": magnitude,
                            "block_number": event.block_number
                        }
                    ))
        
        # Add more pattern detection logic as needed
        return alerts
    
    async def _generate_alerts_for_pattern(self, event: TokenTransferEvent, pattern_type: str, 
                                         detection_data: Dict[str, Any]) -> List[Alert]:
        """
        Generate alerts based on detected patterns
        
        Args:
            event: Token transfer event
            pattern_type: Type of pattern detected
            detection_data: Data about the detection
            
        Returns:
            List[Alert]: Generated alerts
        """
        alerts = []
        chain_id = event.chain_id
        chain_name = self._get_chain_name(chain_id)
        
        if pattern_type == "high_frequency":
            # Generate alert for high frequency trading
            alert_key = f"high_freq:{chain_id}:{event.block_number}"
            
            if self._should_alert(alert_key):
                if detection_data['is_high_network_frequency']:
                    # Network-wide high frequency alert
                    alerts.append(Alert(
                        title=f"High Transfer Frequency on {chain_name}",
                        description=f"High transaction frequency detected on {chain_name}: "
                                    f"{detection_data['network_transfers_per_hour']:.1f} transfers/hour "
                                    f"(threshold: {detection_data['network_threshold']})",
                        severity="medium",
                        source="token_movement_strategy",
                        timestamp=datetime.now(),  # Using current time since we don't rely on timestamp
                        data={
                            "chain_id": chain_id,
                            "chain_name": chain_name,
                            "pattern": "high_frequency_network",
                            "transfers_per_hour": detection_data['network_transfers_per_hour'],
                            "threshold": detection_data['network_threshold'],
                            "window_blocks": detection_data['window_blocks'],
                            "window_hours": detection_data['window_hours'],
                            "block_number": event.block_number
                        }
                    ))
                
                if detection_data['is_high_address_frequency']:
                    # Address-specific high frequency alert
                    address = event.from_address
                    alert_key = f"high_freq_addr:{chain_id}:{address}:{event.block_number}"
                    
                    if self._should_alert(alert_key):
                        alerts.append(Alert(
                            title=f"High Frequency Activity from Address",
                            description=f"Address {address} on {chain_name} shows high frequency activity: "
                                        f"{detection_data['address_transfers_per_hour']:.1f} transfers/hour",
                            severity="medium",
                            source="token_movement_strategy",
                            timestamp=datetime.now(),
                            data={
                                "chain_id": chain_id,
                                "chain_name": chain_name,
                                "pattern": "high_frequency_address",
                                "address": address,
                                "transfers_per_hour": detection_data['address_transfers_per_hour'],
                                "threshold": detection_data['address_threshold'],
                                "window_blocks": detection_data['window_blocks'],
                                "window_hours": detection_data['window_hours'],
                                "block_number": event.block_number
                            }
                        ))
        
        elif pattern_type == "continuous_flow":
            # Generate alert for continuous fund flow
            address = detection_data['address']
            flow_type = "inflow" if detection_data['is_inflow'] else "outflow"
            alert_key = f"flow:{chain_id}:{address}:{flow_type}"
            
            if self._should_alert(alert_key):
                flow_ratio = detection_data['flow_ratio']
                abs_ratio = abs(flow_ratio)
                
                alerts.append(Alert(
                    title=f"Continuous Fund {flow_type} Detected",
                    description=f"Address {address} on {chain_name} shows continuous {flow_type} "
                                f"({abs_ratio:.1%} of total activity)",
                    severity="medium",
                    source="token_movement_strategy",
                    timestamp=datetime.now(),
                    data={
                        "chain_id": chain_id,
                        "chain_name": chain_name,
                        "address": address,
                        "pattern": f"continuous_{flow_type}",
                        "flow_ratio": flow_ratio,
                        "total_inflow": detection_data['total_inflow'],
                        "total_outflow": detection_data['total_outflow'],
                        "net_flow": detection_data['net_flow'],
                        "inflow_count": detection_data['inflow_count'],
                        "outflow_count": detection_data['outflow_count'],
                        "window_blocks": detection_data['window_blocks'],
                        "window_hours": detection_data['window_hours'],
                        "block_number": event.block_number
                    }
                ))
        
        elif pattern_type == "periodic_transfers":
            # Generate alert for periodic transfer pattern
            address = detection_data['address']
            alert_key = f"periodic:{chain_id}:{address}"
            
            if self._should_alert(alert_key):
                # Format description based on token information
                token_info = ""
                if detection_data['token_addresses']:
                    token_symbols = []
                    for token_addr in detection_data['token_addresses']:
                        if token_addr == 'native':
                            token_symbols.append("native tokens")
                        else:
                            # Try to get token symbol
                            token_key = (chain_id, token_addr)
                            if token_key in self.token_stats:
                                symbol = self.token_stats[token_key].get('token_symbol', 'unknown')
                                token_symbols.append(symbol)
                    
                    token_info = f" involving {', '.join(token_symbols)}"
                
                # Get information about frequent recipients
                recipient_info = ""
                if detection_data['frequent_recipients']:
                    recipient_info = f" to {len(detection_data['frequent_recipients'])} frequent recipients"
                
                alerts.append(Alert(
                    title="Periodic Transfer Pattern Detected",
                    description=f"Address {address} on {chain_name} shows periodic outgoing transfers"
                                f"{token_info}{recipient_info} every ~{detection_data['avg_interval_hours']:.1f} hours",
                    severity="medium",
                    source="token_movement_strategy",
                    timestamp=datetime.now(),
                    data={
                        "chain_id": chain_id,
                        "chain_name": chain_name,
                        "address": address,
                        "pattern": "periodic_transfers",
                        "avg_interval_blocks": detection_data['avg_interval_blocks'],
                        "avg_interval_hours": detection_data['avg_interval_hours'],
                        "transfers_count": detection_data['transfers_count'],
                        "token_addresses": detection_data['token_addresses'],
                        "variation": detection_data['variation'],
                        "frequent_recipients": detection_data['frequent_recipients'],
                        "block_number": event.block_number
                    }
                ))
        
        elif pattern_type == "significant_transfer":
            # Generate alert for significant transfer
            alert_key = f"significant:{chain_id}:{event.token_address or 'native'}:{event.transaction_hash}"
            
            if self._should_alert(alert_key):
                alerts.append(Alert(
                    title=f"Significant Transfer: {event.formatted_value} {event.token_symbol or 'tokens'}",
                    description=f"Large transfer of {event.formatted_value} {event.token_symbol or 'tokens'} "
                                f"from {event.from_address} to {event.to_address} on {chain_name}",
                    severity="medium",
                    source="token_movement_strategy",
                    timestamp=datetime.now(),
                    data={
                        "chain_id": chain_id,
                        "chain_name": chain_name,
                        "token_address": event.token_address,
                        "token_symbol": event.token_symbol,
                        "from_address": event.from_address,
                        "to_address": event.to_address,
                        "value": str(event.value),
                        "formatted_value": event.formatted_value,
                        "transaction_hash": event.transaction_hash,
                        "block_number": event.block_number,
                        "pattern": "significant_transfer"
                    }
                ))
        
        return alerts
    
    async def _generate_report(self) -> Optional[Alert]:
        """
        Generate a daily summary report of token movement activity
        
        Returns:
            Optional[Alert]: Report alert or None
        """
        # Skip if we don't have enough data
        if not self.token_stats:
            return None
            
        # Compile report data
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'total_tokens_tracked': len(self.token_stats),
            'total_addresses_tracked': len(self.address_stats),
            'tokens_by_volume': {},
            'addresses_by_activity': {},
        }
        
        # Get top tokens by volume
        top_tokens = sorted(
            self.token_stats.items(), 
            key=lambda x: x[1].get('total_volume', 0), 
            reverse=True
        )[:10]
        
        for (chain_id, token_address), stats in top_tokens:
            token_symbol = stats.get('token_symbol', 'Unknown')
            key = f"{chain_id}:{token_address}"
            report_data['tokens_by_volume'][key] = {
                'chain_id': chain_id,
                'token_address': token_address,
                'token_symbol': token_symbol,
                'total_volume': stats.get('total_volume', 0),
                'transfer_count': stats.get('transfer_count', 0),
                'avg_transfer': stats.get('avg_transfer', 0)
            }
            
        # Get top addresses by activity
        top_addresses = sorted(
            self.address_stats.items(),
            key=lambda x: x[1].get('sent_count', 0) + x[1].get('received_count', 0),
            reverse=True
        )[:10]
        
        for (chain_id, address), stats in top_addresses:
            key = f"{chain_id}:{address}"
            report_data['addresses_by_activity'][key] = {
                'chain_id': chain_id,
                'address': address,
                'sent_count': stats.get('sent_count', 0),
                'received_count': stats.get('received_count', 0),
                'total_sent': stats.get('total_sent', 0),
                'total_received': stats.get('total_received', 0),
                'tokens_count': len(stats.get('tokens_transferred', set())),
                'interactions_count': len(stats.get('interacted_with', set()))
            }
            
        # Create alert
        return Alert(
            title="Token Movement Daily Report",
            description="Daily summary of token movement activity and statistics",
            severity="info",
            source="token_movement_strategy",
            timestamp=datetime.now(),
            data=report_data
        )
    
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
        
        # 创建事件的工作副本用于修改
        modified_event = event
        needs_model_copy = False
        
        # 记录事件基本信息
        logger.debug(f"Processing token transfer: chain={event.chain_id}, tx={event.transaction_hash}, from={event.from_address}, to={event.to_address}")
        
        # 检查是否需要初始化token symbol
        token_symbol = event.token_symbol if hasattr(event, 'token_symbol') else None
        if not token_symbol:
            needs_model_copy = True
            token_symbol = await self._get_token_symbol(event.chain_id, event.token_address or '')
            logger.debug(f"Initialized token symbol: {token_symbol}")
            
        # 检查是否需要初始化formatted value
        formatted_value = event.formatted_value if hasattr(event, 'formatted_value') else None
        if not formatted_value:
            needs_model_copy = True
            formatted_value = await self._format_token_value(
                event.chain_id, 
                event.token_address or '', 
                event.value
            )
            logger.debug(f"Initialized formatted value: {formatted_value}")
        
        # 如果需要修改，创建模型的副本并更新字段
        if needs_model_copy:
            try:
                # 使用model_copy方法创建可修改的副本 (Pydantic v2 语法)
                modified_event = event.model_copy(update={
                    "token_symbol": token_symbol or event.token_symbol,
                    "formatted_value": formatted_value or event.formatted_value
                })
                logger.debug("Created modified event using model_copy")
            except AttributeError:
                # 如果是Pydantic v1，使用copy方法
                try:
                    modified_event = event.copy(update={
                        "token_symbol": token_symbol or event.token_symbol,
                        "formatted_value": formatted_value or event.formatted_value
                    })
                    logger.debug("Created modified event using copy")
                except AttributeError:
                    # 如果以上方法都失败，记录错误并继续使用原始事件
                    logger.error(f"Unable to update event fields due to Pydantic model restrictions")
            
        # Analyze the event and generate alerts
        alerts = await self.analyze_event(modified_event)
        
        if alerts:
            logger.info(f"Generated {len(alerts)} alerts for token transfer: chain={event.chain_id}, tx={event.transaction_hash}, value={formatted_value} {token_symbol}")
        
        return alerts
        
    async def _get_token_symbol(self, chain_id: int, token_address: str) -> str:
        """
        Get the symbol for a token
        
        Args:
            chain_id: Blockchain ID
            token_address: Token contract address
            
        Returns:
            str: Token symbol or 'Unknown'
        """
        # Return native token symbol if this is a native token transfer
        if not token_address or token_address == '0x0000000000000000000000000000000000000000':
            # Map chain ID to native token symbol
            native_symbols = {
                1: 'ETH',    # Ethereum
                56: 'BNB',   # Binance Smart Chain
                137: 'MATIC', # Polygon
                10: 'ETH',   # Optimism
                42161: 'ETH', # Arbitrum
                43114: 'AVAX' # Avalanche
            }
            return native_symbols.get(chain_id, 'Native')
            
        # For other tokens, we'd need to query the blockchain or a database
        # This is a placeholder implementation
        token_key = f"{chain_id}:{token_address.lower()}"
        
        # Check cache first
        if token_key in self.token_symbols_cache:
            return self.token_symbols_cache[token_key]
            
        # For now, just return a placeholder
        # In a real implementation, you'd query the token contract
        return 'ERC20'
        
    async def _format_token_value(self, chain_id: int, token_address: str, value: int) -> float:
        """
        Format a token value using the correct decimals
        
        Args:
            chain_id: Blockchain ID
            token_address: Token contract address
            value: Raw token value
            
        Returns:
            float: Formatted token value
        """
        # Default decimals for common native tokens
        native_decimals = {
            1: 18,     # Ethereum (ETH)
            56: 18,    # Binance Smart Chain (BNB)
            137: 18,   # Polygon (MATIC)
            10: 18,    # Optimism (ETH)
            42161: 18, # Arbitrum (ETH)
            43114: 18  # Avalanche (AVAX)
        }
        
        # If this is a native token transfer, use default decimals
        if not token_address or token_address == '0x0000000000000000000000000000000000000000':
            decimals = native_decimals.get(chain_id, 18)
            return float(value) / (10 ** decimals)
            
        # For other tokens, we'd need to query the blockchain or a database
        # This is a placeholder implementation
        token_key = f"{chain_id}:{token_address.lower()}"
        
        # Check cache first
        if token_key in self.token_decimals_cache:
            decimals = self.token_decimals_cache[token_key]
        else:
            # Default to 18 decimals for most ERC20 tokens
            decimals = 18
            
        return float(value) / (10 ** decimals)
    
    async def analyze_event(self, event: TokenTransferEvent) -> List[Alert]:
        """
        Main entry point for analyzing a token transfer event.
        This method coordinates all detection mechanisms and aggregates alerts.
        
        Args:
            event: The token transfer event to analyze
            
        Returns:
            List[Alert]: A list of alerts generated from this event
        """
        # Skip if this event should be filtered
        if not self._should_track_transfer(event):
            logger.debug(f"Skipping transfer tracking: chain={event.chain_id}, tx={event.transaction_hash}")
            return []
            
        # Collect alerts from all detection mechanisms
        alerts = []
        
        # Track the transfer in our statistics
        self._update_statistics(event)
        
        # Special handling for watched addresses - always alert
        is_watched_from = self._is_watched_address(event.chain_id, event.from_address)
        is_watched_to = self._is_watched_address(event.chain_id, event.to_address)
        
        if is_watched_from or is_watched_to:
            chain_name = self._get_chain_name(event.chain_id)
            logger.info(f"Transfer involving watched address detected: {event.from_address if is_watched_from else event.to_address}")
            
            alerts.append(Alert(
                title="Significant Token Transfer",
                description=f"Transfer involving watched address {'from ' + event.from_address if is_watched_from else 'to ' + event.to_address}",
                severity="medium",
                source="token_movement_strategy",
                timestamp=datetime.now(),
                data={
                    "chain_id": event.chain_id,
                    "chain_name": chain_name,
                    "token_symbol": event.token_symbol,
                    "token_address": event.token_address,
                    "from_address": event.from_address,
                    "to_address": event.to_address,
                    "from_watched": is_watched_from,
                    "to_watched": is_watched_to,
                    "value": str(event.value),
                    "formatted_value": event.formatted_value,
                    "transaction_hash": event.transaction_hash,
                    "block_number": event.block_number
                }
            ))
        
        # 1. Check for unusual patterns (blacklists, unusual transfers)
        unusual_alerts = await self._check_for_unusual_patterns(event)
        if unusual_alerts:
            logger.info(f"Detected {len(unusual_alerts)} unusual patterns for tx {event.transaction_hash}")
        alerts.extend(unusual_alerts)
        
        # 2. Check for high-frequency trading
        high_freq_result = self._detect_high_frequency_trading(event)
        if high_freq_result:
            logger.info(f"High-frequency trading detected for address {event.from_address}: {high_freq_result['transfer_count']} transfers in {high_freq_result['time_frame']} blocks")
            alerts.append(Alert(
                title="High-Frequency Trading Detected",
                description=f"Address {event.from_address} has made {high_freq_result['transfer_count']} transfers in {high_freq_result['time_frame']} blocks",
                severity="medium",
                source="token_movement_strategy",
                timestamp=datetime.now(),
                data={
                    **high_freq_result,
                    "chain_id": event.chain_id,
                    "chain_name": self._get_chain_name(event.chain_id),
                    "from_address": event.from_address,
                    "transaction_hash": event.transaction_hash,
                    "block_number": event.block_number
                }
            ))
            
        # 3. Check for continuous fund flow
        flow_result = self._detect_continuous_flow(event)
        if flow_result:
            flow_type = flow_result['flow_type']
            pattern_type = flow_result.get('pattern_type', 'consistent')
            net_flow = abs(flow_result.get('net_flow', 0))
            
            logger.info(f"Continuous {flow_type.lower()} detected for address {event.from_address}: pattern={pattern_type}, net_flow={net_flow} {flow_result.get('token_symbol', 'tokens')}")
            
            # 调整警报严重程度，根据金额大小设置
            if net_flow > self.significant_threshold * 10:  # 非常大的金额
                severity = "high"
            elif net_flow > self.significant_threshold:
                severity = "medium"
            else:
                severity = "info"
                
            # 根据模式类型构建不同的描述
            if pattern_type == 'short_term_consecutive':
                recent_count = flow_result.get('recent_transactions_count', 5)
                recent_amount = flow_result.get('recent_amount', 0)
                description = (f"Address {event.from_address} shows {recent_count} consecutive "
                              f"{flow_type.lower()} transactions of {flow_result.get('token_symbol', 'tokens')} "
                              f"totaling {recent_amount:.2f}")
                title = f"Short-term Consecutive {flow_type} Pattern"
            else:  # long_term_biased 或其他
                transaction_count = flow_result.get('transaction_count', 0)
                flow_ratio = abs(flow_result.get('flow_ratio', 0)) * 100
                description = (f"Address {event.from_address} shows consistent {flow_type.lower()} pattern "
                              f"({flow_ratio:.1f}% of activity) of {flow_result.get('token_symbol', 'tokens')} "
                              f"across {transaction_count} transactions, "
                              f"net {flow_type.lower()}: {net_flow:.2f}")
                title = f"Consistent {flow_type} Pattern Detected"
            
            alerts.append(Alert(
                title=title,
                description=description,
                severity=severity,
                source="token_movement_strategy",
                timestamp=datetime.now(),
                data={
                    **flow_result,
                    "chain_id": event.chain_id,
                    "chain_name": self._get_chain_name(event.chain_id),
                    "transaction_hash": event.transaction_hash,
                    "block_number": event.block_number
                }
            ))
            
        # 4. Check for periodic transfers (like mining rewards)
        periodic_result = self._detect_periodic_transfers(event)
        if periodic_result:
            logger.info(f"Periodic transfer pattern detected for address {event.from_address}: ~{periodic_result['avg_interval_hours']:.1f} hours interval")
            alerts.append(Alert(
                title="Periodic Transfer Pattern Detected",
                description=f"Address {event.from_address} shows regular transfers every ~{periodic_result['avg_interval_hours']:.1f} hours",
                severity="medium",
                source="token_movement_strategy",
                timestamp=datetime.now(),
                data={
                    **periodic_result,
                    "chain_id": event.chain_id,
                    "chain_name": self._get_chain_name(event.chain_id),
                    "transaction_hash": event.transaction_hash,
                    "block_number": event.block_number
                }
            ))
            
        # 5. Check if this is a significant transfer
        if self._is_significant_transfer(event):
            logger.info(f"Significant transfer detected: {event.formatted_value} {event.token_symbol or 'native tokens'}")
            alerts.append(Alert(
                title="Significant Token Transfer",
                description=f"Large transfer of {event.formatted_value} {event.token_symbol or 'native tokens'} detected",
                severity="medium",
                source="token_movement_strategy",
                timestamp=datetime.now(),
                data={
                    "chain_id": event.chain_id,
                    "chain_name": self._get_chain_name(event.chain_id),
                    "token_symbol": event.token_symbol,
                    "token_address": event.token_address,
                    "from_address": event.from_address,
                    "to_address": event.to_address,
                    "value": str(event.value),
                    "formatted_value": event.formatted_value,
                    "transaction_hash": event.transaction_hash,
                    "block_number": event.block_number
                }
            ))
                
        # Apply rate limiting and deduplication
        final_alerts = self._deduplicate_alerts(alerts)
        
        if len(final_alerts) < len(alerts):
            logger.debug(f"Deduplicated alerts: {len(alerts)} -> {len(final_alerts)}")
        
        # 记录生成的警报类型
        if final_alerts:
            alert_types = [alert.title for alert in final_alerts]
            logger.info(f"Alert types generated: {', '.join(alert_types)}")
        
        return final_alerts
        
    def _should_track_transfer(self, event: TokenTransferEvent) -> bool:
        """
        Determine if a transfer should be tracked and analyzed
        
        Args:
            event: Token transfer event
            
        Returns:
            bool: Whether to track and analyze this transfer
        """
        # Always track transfers involving watched addresses or tokens
        if (self._is_watched_address(event.chain_id, event.from_address) or
            self._is_watched_address(event.chain_id, event.to_address) or
            self._is_watched_token(event.chain_id, event.token_address)):
            return True
            
        # Check if it's a significant transfer
        if self._is_significant_transfer(event):
            return True
            
        # Check if it's an unusual transfer (statistically)
        if self._is_unusual_transfer(event):
            return True
            
        # By default, track all transfers
        return True
        
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
            
        # 记录最终生成的alerts类型和数量
        if deduplicated:
            alert_types_count = {}
            for alert in deduplicated:
                alert_types_count[alert.title] = alert_types_count.get(alert.title, 0) + 1
                
            logger.debug(f"Alert types after deduplication: {alert_types_count}")
        
        return deduplicated

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
        
        # 记录处理开始
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
                
        # Generate and append daily report if configured
        if self.daily_report:
            # Check if it's time for a report
            now = datetime.now()
            if (now - self.last_report_time).total_seconds() > 86400:  # 24 hours in seconds
                logger.info("Generating daily token movement report")
                report_alert = await self._generate_report()
                if report_alert:
                    all_alerts.append(report_alert)
                    logger.info("Daily token movement report generated")
                self.last_report_time = now
        
        # 记录处理结果
        if all_alerts:
            logger.info(f"TokenMovementStrategy.process: Processed {token_transfer_count}/{len(events)} token transfers, generated {len(all_alerts)} alerts/actions")
        else:
            logger.debug(f"TokenMovementStrategy.process: Processed {token_transfer_count}/{len(events)} token transfers, no alerts generated")
            
        return all_alerts
        
    def _should_filter_transfer(self, event: TokenTransferEvent) -> bool:
        """
        Determine if a transfer should be filtered out (ignored) based on various criteria
        
        Args:
            event: Token transfer event
            
        Returns:
            bool: Whether to filter this transfer
        """
        # Always process transfers involving watched addresses/tokens
        if (self._is_watched_address(event.chain_id, event.from_address) or
            self._is_watched_address(event.chain_id, event.to_address) or
            self._is_watched_token(event.chain_id, event.token_address)):
            return False
            
        # Filter out transfers involving whitelisted addresses (unless explicitly configured not to)
        if (self._is_whitelisted_address(event.chain_id, event.from_address) or
            self._is_whitelisted_address(event.chain_id, event.to_address)):
            return True
            
        # If filtering small transfers is enabled
        if self.filter_small_transfers:
            token_key = (event.chain_id, event.token_address or 'native')
            stats = self.token_stats.get(token_key, {})
            
            # If we have stats for this token
            if stats and 'avg_transfer' in stats and stats['transfer_count'] > self.anomaly_window_size:
                avg_transfer = stats['avg_transfer']
                
                # Filter out transfers that are too small (less than 10% of average)
                if event.formatted_value < (avg_transfer * 0.1):
                    return True
        
        # By default, don't filter
        return False
        
    def _is_likely_dex_trade(self, event: TokenTransferEvent) -> bool:
        """
        Check if a transfer is likely part of a DEX trade
        
        Args:
            event: Token transfer event
            
        Returns:
            bool: Whether this appears to be a DEX trade
        """
        # If either address is a known DEX, it's likely a DEX trade
        if (self._is_whitelisted_address(event.chain_id, event.from_address) or
            self._is_whitelisted_address(event.chain_id, event.to_address)):
            return True
            
        # Check for common DEX patterns
        # 1. Round number transfers (common in swaps)
        value = event.formatted_value
        is_round_number = (value == int(value) or 
                          abs(value - round(value, 1)) < 0.01 or
                          abs(value - round(value, -1)) < 1)
            
        # 2. Common swap amounts like 0.1, 1, 10, 100, etc.
        common_swap_amounts = [0.1, 0.5, 1, 5, 10, 50, 100, 500, 1000]
        is_common_amount = any(abs(value - amt) / amt < 0.05 for amt in common_swap_amounts if amt > 0)
        
        # If it meets multiple criteria, it's likely a DEX trade
        return is_round_number or is_common_amount
        
    def _is_whitelisted_address(self, chain_id: int, address: str) -> bool:
        """
        Check if an address is on the whitelist (typically DEXs, known protocols)
        
        Args:
            chain_id: Blockchain ID
            address: Address to check
            
        Returns:
            bool: Whether the address is whitelisted
        """
        # Check user-configured whitelist
        chain_str = str(chain_id)
        if chain_str in self.whitelist_addresses:
            if address.lower() in [a.lower() for a in self.whitelist_addresses[chain_str]]:
                return True
                
        # Check known DEXes
        if chain_id in self.known_dexes:
            if address.lower() in [a.lower() for a in self.known_dexes[chain_id]]:
                return True
                
        return False
        
    def _is_watched_address(self, chain_id: int, address: str) -> bool:
        """Check if the address is in our watch list for the given chain."""
        if not self.watch_addresses:
            return False
        
        chain_str = str(chain_id)
        if chain_str not in self.watch_addresses:
            return False
        
        watched_addresses = [addr.lower() for addr in self.watch_addresses[chain_str]]
        return address.lower() in watched_addresses
        
    def _is_watched_token(self, chain_id: int, token_address: Optional[str]) -> bool:
        """Check if the token is in our watch list for the given chain."""
        if not self.watch_tokens:
            return False
        
        chain_str = str(chain_id)
        if chain_str not in self.watch_tokens:
            return False
        
        token_address = token_address or 'native'
        watched_tokens = [addr.lower() for addr in self.watch_tokens[chain_str]]
        return token_address.lower() in watched_tokens or 'native' in watched_tokens
        
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
        
    def _is_stablecoin(self, chain_id: int, token_address: str, token_symbol: str) -> bool:
        """
        Determine if a token is a stablecoin
        
        Args:
            chain_id: Blockchain ID
            token_address: Token contract address
            token_symbol: Token symbol
            
        Returns:
            bool: Whether the token is a stablecoin
        """
        # Common stablecoin symbols
        stablecoin_symbols = ['USDT', 'USDC', 'DAI', 'BUSD', 'TUSD', 'UST', 'GUSD', 'USDP', 'FRAX']
        if token_symbol in stablecoin_symbols:
            return True
            
        # Well-known stablecoin addresses by chain
        stablecoin_addresses = {
            1: [  # Ethereum
                '0xdac17f958d2ee523a2206206994597c13d831ec7',  # USDT
                '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',  # USDC
                '0x6b175474e89094c44da98b954eedeac495271d0f',  # DAI
                '0x4fabb145d64652a948d72533023f6e7a623c7c53',  # BUSD
                '0x0000000000085d4780b73119b644ae5ecd22b376',  # TUSD
                '0x956f47f50a910163d8bf957cf5846d573e7f87ca',  # FEI
                '0xa47c8bf37f92abed4a126bda807a7b7498661acd',  # WUST
                '0x853d955acef822db058eb8505911ed77f175b99e',  # FRAX
            ],
            56: [  # BSC
                '0x55d398326f99059ff775485246999027b3197955',  # BSC-USDT
                '0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d',  # BSC-USDC
                '0x1af3f329e8be154074d8769d1ffa4ee058b1dbc3',  # BSC-DAI
                '0xe9e7cea3dedca5984780bafc599bd69add087d56',  # BUSD
            ],
            137: [  # Polygon
                '0xc2132d05d31c914a87c6611c10748aeb04b58e8f',  # USDT
                '0x2791bca1f2de4661ed88a30c99a7a9449aa84174',  # USDC
                '0x8f3cf7ad23cd3cadbd9735aff958023239c6a063',  # DAI
                '0x9C9e5fD8bbc25984B178FdCE6117Defa39d2db39',  # BUSD
            ],
            10: [  # Optimism
                '0x94b008aa00579c1307b0ef2c499ad98a8ce58e58',  # USDT
                '0x7f5c764cbc14f9669b88837ca1490cca17c31607',  # USDC
                '0xda10009cbd5d07dd0cecc66161fc93d7c9000da1',  # DAI
            ],
            42161: [  # Arbitrum
                '0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9',  # USDT
                '0xff970a61a04b1ca14834a43f5de4533ebddb5cc8',  # USDC
                '0xda10009cbd5d07dd0cecc66161fc93d7c9000da1',  # DAI
            ]
        }
        
        if chain_id in stablecoin_addresses and token_address and token_address.lower() in stablecoin_addresses[chain_id]:
            return True
            
        return False
        
    def _is_significant_transfer(self, event: TokenTransferEvent) -> bool:
        """
        Check if a transfer is significant based on thresholds
        
        Args:
            event: Token transfer event
            
        Returns:
            bool: Whether it's a significant transfer
        """
        # If no thresholds are set or we don't have a token symbol to check against, use defaults
        if not self.significant_transfer_threshold or not event.token_symbol:
            # Check if it's a stablecoin - use higher default threshold
            if event.token_symbol and self._is_stablecoin(event.chain_id, event.token_address or '', event.token_symbol):
                return event.formatted_value >= 50000.0  # Higher threshold for stablecoins (e.g., $5000)
            else:
                return event.formatted_value >= 100.0  # Default threshold for non-stablecoins
            
        chain_id = event.chain_id
        chain_str = str(chain_id)
        
        # Check if we have thresholds for this chain
        if chain_str not in self.significant_transfer_threshold:
            # Use default thresholds
            if self._is_stablecoin(event.chain_id, event.token_address or '', event.token_symbol):
                return event.formatted_value >= 5000.0  # Higher threshold for stablecoins
            else:
                return event.formatted_value >= 100.0  # Default threshold for non-stablecoins
            
        # Get token-specific threshold
        chain_thresholds = self.significant_transfer_threshold[chain_str]
        
        # If no threshold for this token, use a default if available
        if event.token_symbol not in chain_thresholds:
            if 'DEFAULT' in chain_thresholds:
                threshold = chain_thresholds['DEFAULT']
            else:
                # No default threshold, use stablecoin logic
                if self._is_stablecoin(event.chain_id, event.token_address or '', event.token_symbol):
                    return event.formatted_value >= 5000.0  # Higher threshold for stablecoins
                else:
                    return event.formatted_value >= 100.0  # Default threshold for non-stablecoins
        else:
            threshold = chain_thresholds[event.token_symbol]
            
        return event.formatted_value >= threshold
        
    def _detect_high_frequency_trading(self, event: TokenTransferEvent) -> Optional[Dict[str, Any]]:
        """
        Detect high frequency transfer activity
        
        Args:
            event: Token transfer event
            
        Returns:
            Optional[Dict[str, Any]]: Detection results or None
        """
        chain_id = event.chain_id
        block_number = event.block_number
        
        # Check if we've already analyzed this block
        if chain_id in self.last_checked_block and self.last_checked_block[chain_id] >= block_number:
            return None
            
        # Update last checked block
        self.last_checked_block[chain_id] = block_number
        
        # Define high frequency window based on block times
        # For example, 100 blocks on Ethereum (~25 min), 500 on BSC (~25 min)
        high_frequency_window_blocks = 100  # Default
        
        # Set window blocks based on chain
        if hasattr(self, 'BLOCK_TIMES') and chain_id in self.BLOCK_TIMES:
            # Try to get a window of approximately 30 minutes
            block_time = self.BLOCK_TIMES.get(chain_id, 15)  # Default to 15 seconds
            high_frequency_window_blocks = max(20, int(1800 / block_time))  # At least 20 blocks
        
        # Calculate block window for analysis
        start_block = max(0, block_number - high_frequency_window_blocks)
        
        # Calculate address-specific frequency
        address_key = (chain_id, event.from_address)
        address_transfers = sum(
            count for blk, count in self.address_transfers_by_block[address_key].items()
            if start_block <= blk <= block_number
        )
        
        # Estimate time for window in hours
        window_seconds = self._estimate_time_from_blocks(chain_id, high_frequency_window_blocks)
        window_hours = window_seconds / 3600  # Convert to hours
        
        # Set threshold based on address type (different expectations for different addresses)
        threshold = 20  # Default: 20 transfers per 30 min window
        
        # If this is a high frequency trading pattern
        if address_transfers >= threshold:
            return {
                'address': event.from_address,
                'transfer_count': address_transfers,
                'time_frame': high_frequency_window_blocks,
                'time_frame_hours': window_hours,
                'threshold': threshold,
                'is_high_frequency': True
            }
        
        return None
        
    def _detect_continuous_flow(self, event: TokenTransferEvent) -> Optional[Dict[str, Any]]:
        """
        Detect continuous fund inflow or outflow for an address
        
        Args:
            event: Token transfer event
            
        Returns:
            Optional[Dict[str, Any]]: Detection results or None
        """
        chain_id = event.chain_id
        address = event.from_address
        
        # Get address key
        address_key = (chain_id, address)
        
        # Ensure we have statistics for this address
        if address_key not in self.address_stats:
            return None
            
        stats = self.address_stats[address_key]
        
        # Check if we have enough history (minimum 5 transactions)
        if stats['sent_count'] + stats['received_count'] < 5:
            return None
            
        # Calculate inflow and outflow
        total_inflow = stats['total_received']
        total_outflow = stats['total_sent']
        
        # Calculate net flow and total flow
        net_flow = total_inflow - total_outflow
        total_flow = total_inflow + total_outflow
        
        # 1. 金额阈值检查 - 按货币类型区分最小有意义金额
        # 获取涉及的代币类型
        token_symbols = [self._get_token_symbol_from_cache(chain_id, token) for token in stats['tokens_transferred']]
        token_symbols = list(filter(None, token_symbols))
        token_symbol = ', '.join(token_symbols) or 'various tokens'
        
        # 设置金额阈值
        min_significant_amount = 50.0  # 默认最小阈值 $50
        
        # 对稳定币使用更高阈值
        has_stablecoin = any(symbol in ['USDC', 'USDT', 'DAI', 'BUSD', 'TUSD', 'UST'] for symbol in token_symbols)
        if has_stablecoin:
            min_significant_amount = 500.0  # 稳定币最小阈值 $500
        
        # 对高价值代币使用不同阈值
        has_high_value_token = any(symbol in ['ETH', 'BTC', 'BNB'] for symbol in token_symbols)
        if has_high_value_token:
            min_significant_amount = 200.0  # 高价值代币最小阈值 $200
            
        # 如果净流动低于阈值，不触发警报
        if abs(net_flow) < min_significant_amount:
            return None
            
        # 2. 连续性检查
        # 获取该地址的交易历史
        address_transfers = self.transfers_by_address.get(address_key, [])
        
        # 短期连续行为检测：检查最近5笔交易方向是否一致
        recent_transfers = sorted(address_transfers, key=lambda t: t.block_number, reverse=True)[:5]
        
        if len(recent_transfers) >= 5:
            # 检查短时间内连续转入或转出
            is_outflow = [t.from_address == address for t in recent_transfers]
            is_inflow = [t.to_address == address for t in recent_transfers]
            
            consecutive_outflow = all(is_outflow)
            consecutive_inflow = all(is_inflow)
            
            if consecutive_outflow or consecutive_inflow:
                flow_type = "Outflow" if consecutive_outflow else "Inflow"
                # 计算最近5笔交易的总金额
                recent_amount = sum(t.formatted_value for t in recent_transfers)
                
                # 确保短期连续交易的总金额也满足最小阈值
                if recent_amount >= min_significant_amount:
                    return {
                        'address': address,
                        'flow_type': flow_type,
                        'pattern_type': 'short_term_consecutive',
                        'flow_ratio': 1.0 if flow_type == "Inflow" else -1.0,
                        'total_inflow': total_inflow,
                        'total_outflow': total_outflow,
                        'net_flow': net_flow,
                        'token_symbol': token_symbol,
                        'recent_transactions_count': len(recent_transfers),
                        'recent_amount': recent_amount
                    }
                
        # 3. 长期模式检测 - 按比例的单向流动
        # 计算流动比例 (正值表示净流入，负值表示净流出)
        if total_flow < 0.01:  # 避免除以零
            return None
            
        flow_ratio = net_flow / total_flow
        
        # 检查是否严重偏向单一方向 (超过80%)
        if abs(flow_ratio) > 0.8 and abs(net_flow) >= min_significant_amount:
            # 确保交易总量满足最低要求
            min_transaction_count = 10  # 长期模式至少需要10笔交易
            if stats['sent_count'] + stats['received_count'] < min_transaction_count:
                return None
                
            flow_type = "Inflow" if flow_ratio > 0 else "Outflow"
            
            return {
                'address': address,
                'flow_type': flow_type,
                'pattern_type': 'long_term_biased',
                'flow_ratio': flow_ratio,
                'total_inflow': total_inflow,
                'total_outflow': total_outflow,
                'net_flow': net_flow,
                'token_symbol': token_symbol,
                'transaction_count': stats['sent_count'] + stats['received_count']
            }
        
        return None
        
    def _get_token_symbol_from_cache(self, chain_id: int, token_address: str) -> Optional[str]:
        """
        Get token symbol from cache if available
        
        Args:
            chain_id: Blockchain ID
            token_address: Token address or 'native'
            
        Returns:
            Optional[str]: Token symbol or None if not found
        """
        if token_address == 'native':
            # Map chain ID to native token symbol
            native_symbols = {
                1: 'ETH',    # Ethereum
                56: 'BNB',   # Binance Smart Chain
                137: 'MATIC', # Polygon
                10: 'ETH',   # Optimism
                42161: 'ETH', # Arbitrum
                43114: 'AVAX' # Avalanche
            }
            return native_symbols.get(chain_id, 'Native')
            
        # Check if we have this token in our statistics
        token_key = (chain_id, token_address)
        if token_key in self.token_stats:
            return self.token_stats[token_key].get('token_symbol')
            
        return None
        
    def _detect_periodic_transfers(self, event: TokenTransferEvent) -> Optional[Dict[str, Any]]:
        """
        Detect periodic transfer patterns (like mining rewards withdrawals)
        
        Args:
            event: Token transfer event
            
        Returns:
            Optional[Dict[str, Any]]: Detection results or None
        """
        # Default parameter
        periodic_sale_detection = True
        min_periodic_occurrences = 3
        
        if not periodic_sale_detection:
            return None
            
        chain_id = event.chain_id
        address = event.from_address
        
        # Only check outgoing transfers for periodic patterns
        if event.to_address is None:
            return None
            
        # Get address key
        address_key = (chain_id, address)
        
        # Ensure we have enough transfer history
        if address_key not in self.transfers_by_address:
            return None
            
        # Get all outgoing transfers for this address
        outgoing_transfers = [
            t for t in self.transfers_by_address[address_key]
            if t.from_address == address
        ]
        
        # Need minimum number of transfers to detect pattern
        if len(outgoing_transfers) < min_periodic_occurrences:
            return None
            
        # Sort by block number
        outgoing_transfers.sort(key=lambda t: t.block_number)
        
        # Extract block numbers
        block_numbers = [t.block_number for t in outgoing_transfers]
        
        # Calculate block intervals between transfers
        intervals = [
            block_numbers[i+1] - block_numbers[i]
            for i in range(len(block_numbers) - 1)
        ]
        
        # Need at least 2 intervals for pattern detection
        if len(intervals) < 2:
            return None
            
        # Check if the intervals are similar (consistent pattern)
        if len(intervals) >= 2:
            # Calculate average and standard deviation of intervals
            avg_interval = sum(intervals) / len(intervals)
            
            # Calculate variation
            if avg_interval > 0:
                variations = [abs(i - avg_interval) / avg_interval for i in intervals]
                avg_variation = sum(variations) / len(variations)
                
                # If consistent interval pattern detected
                if avg_variation < 0.3:  # Allow 30% variation in interval
                    # Estimate interval in hours
                    interval_hours = self._estimate_time_from_blocks(chain_id, int(avg_interval)) / 3600
                    
                    # Get token addresses involved
                    token_addresses = {t.token_address or 'native' for t in outgoing_transfers}
                    
                    # Get common recipient addresses if any
                    recipient_counts = {}
                    for t in outgoing_transfers:
                        if t.to_address:
                            recipient_counts[t.to_address] = recipient_counts.get(t.to_address, 0) + 1
                            
                    # Find frequent recipients (receiving > 50% of transfers)
                    frequent_recipients = [
                        addr for addr, count in recipient_counts.items()
                        if count > len(outgoing_transfers) * 0.5
                    ]
                    
                    return {
                        'address': address,
                        'pattern_type': 'periodic_outgoing',
                        'avg_interval_blocks': avg_interval,
                        'avg_interval_hours': interval_hours,
                        'transfers_count': len(outgoing_transfers),
                        'token_addresses': list(token_addresses),
                        'variation': avg_variation,
                        'frequent_recipients': frequent_recipients
                    }
        
        return None
        
    def _is_blacklisted_address(self, chain_id: int, address: str) -> bool:
        """
        Check if an address is in the blacklist
        
        Args:
            chain_id: Blockchain ID
            address: Address to check
            
        Returns:
            bool: Whether the address is blacklisted
        """
        if not self.blacklist_addresses:
            return False
            
        chain_str = str(chain_id)
        
        # Check if we have a blacklist for this chain
        if chain_str not in self.blacklist_addresses:
            return False
            
        # Check if the address is in the blacklist
        return address.lower() in [addr.lower() for addr in self.blacklist_addresses[chain_str]]

    def _is_unusual_transfer(self, event: TokenTransferEvent) -> bool:
        """
        Determine if a transfer is unusual based on historical data
        
        Args:
            event: Token transfer event
            
        Returns:
            bool: Whether the transfer is unusual
        """
        # Skip if we don't have enough history
        token_key = (event.chain_id, event.token_address or 'native')
        if token_key not in self.token_stats:
            return False
            
        stats = self.token_stats[token_key]
        
        # Skip if we don't have enough history
        if stats.get('transfer_count', 0) < self.anomaly_window_size:
            # Not enough transfer history to determine if unusual
            return False
            
        # Check if the value is unusual (outside expected range)
        mean = stats.get('mean_value', 0)
        stdev = stats.get('stdev_value', 0)
        
        # If we don't have valid statistics, can't determine if unusual
        if mean <= 0 or stdev <= 0:
            return False
            
        # Calculate z-score
        z_score = (event.formatted_value - mean) / stdev
        
        # Return true if the z-score exceeds our threshold
        return z_score > self.unusual_volume_threshold

    async def analyze(self, event: TokenTransferEvent) -> List[Alert]:
        """
        Analyze a token transfer event and generate alerts
        This is an alias for analyze_event to maintain backward compatibility with tests
        
        Args:
            event: Token transfer event to analyze
            
        Returns:
            List[Alert]: Generated alerts
        """
        return await self.analyze_event(event) 