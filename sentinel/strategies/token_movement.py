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
    
    The strategy maintains statistics on token transfers and can generate alerts
    for unusual or significant activity. It can also generate reports for
    visualization and analysis of token movements over time.
    """
    
    __component_name__ = "token_movement"
    
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
        
        # Track token transfers
        self.transfers_by_token: Dict[Tuple[int, str], List[TokenTransferEvent]] = defaultdict(list)
        self.transfers_by_address: Dict[Tuple[int, str], List[TokenTransferEvent]] = defaultdict(list)
        
        # Last alert timestamps to prevent alert spam
        self.last_alert_time: Dict[str, float] = {}
        
        # Statistics
        self.token_stats: Dict[Tuple[int, str], Dict[str, Any]] = {}
        self.address_stats: Dict[Tuple[int, str], Dict[str, Any]] = {}
        
        # Chain metadata
        self.chain_metadata: Dict[int, Dict[str, Any]] = {}
        
        # Initialize reporting
        self.last_report_time = datetime.now()
    
    async def _start(self):
        """Strategy initialization on startup"""
        logger.info("Starting TokenMovementStrategy")
    
    async def _stop(self):
        """Cleanup on shutdown"""
        if self.daily_report:
            # Generate final report on shutdown
            await self._generate_report()
    
    def _should_alert(self, alert_key: str) -> bool:
        """
        Check if we should send an alert or if it's too soon
        
        Args:
            alert_key: Unique key for this type of alert
            
        Returns:
            bool: Whether to send the alert
        """
        if not self.throttle_alerts:
            return True
            
        current_time = time.time()
        last_time = self.last_alert_time.get(alert_key, 0)
        
        if current_time - last_time > self.alert_cooldown:
            self.last_alert_time[alert_key] = current_time
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
        # If no thresholds are set, consider all transfers significant
        if not self.significant_transfer_threshold:
            return True
            
        chain_id = event.chain_id
        chain_str = str(chain_id)
        
        # Check if we have thresholds for this chain
        if chain_str not in self.significant_transfer_threshold:
            return True
            
        # Get token-specific threshold
        token_symbol = event.token_symbol
        if not token_symbol:
            return True
            
        chain_thresholds = self.significant_transfer_threshold[chain_str]
        
        # If no threshold for this token, use a default if available
        if token_symbol not in chain_thresholds and 'DEFAULT' in chain_thresholds:
            threshold = chain_thresholds['DEFAULT']
        elif token_symbol in chain_thresholds:
            threshold = chain_thresholds[token_symbol]
        else:
            # No threshold set, consider it significant
            return True
            
        return event.formatted_value >= threshold
    
    def _is_unusual_transfer(self, event: TokenTransferEvent) -> bool:
        """
        Determine if a transfer is unusual based on historical data.
        A transfer is considered unusual if it's significantly larger than the average
        for this token or if it comes from an address that rarely makes transfers.
        """
        # Skip if not a token transfer
        if not isinstance(event, TokenTransferEvent):
            return False
        
        # Get token stats
        token_key = (event.chain_id, event.token_address or 'native')
        stats = self.token_stats.get(token_key, {})
        
        # If we don't have enough data, use the significance threshold
        if not stats or stats.get('transfer_count', 0) < self.anomaly_window_size:
            return self._is_significant_transfer(event)
        
        # Get statistics
        avg_transfer = stats.get('avg_transfer', 0)
        mean_value = stats.get('mean_value', 0)
        stdev_value = stats.get('stdev_value', 0)
        max_transfer = stats.get('max_transfer', 0)
        
        # Use the current transfer value
        value = event.formatted_value or 0
        
        # A transfer is unusual if:
        # 1. It's more than 3 standard deviations from the mean (if we have std dev)
        if stdev_value > 0:
            if value > mean_value + (3 * stdev_value):
                return True
        
        # 2. It's at least 5 times larger than the average
        if avg_transfer > 0 and value > (avg_transfer * 5):
            return True
        
        # 3. It's within 10% of the maximum transfer we've seen (if it's significant)
        if max_transfer > 0 and value > (max_transfer * 0.9) and self._is_significant_transfer(event):
            return True
        
        # Not unusual based on our criteria
        return False
    
    def _is_blacklisted_address(self, chain_id: int, address: str) -> bool:
        """
        Check if an address is on the blacklist
        
        Args:
            chain_id: Blockchain ID
            address: Address to check
            
        Returns:
            bool: Whether the address is blacklisted
        """
        chain_str = str(chain_id)
        if chain_str not in self.blacklist_addresses:
            return False
            
        return address.lower() in [a.lower() for a in self.blacklist_addresses[chain_str]]
    
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
        
        # Check if addresses involved are blacklisted
        from_blacklisted = self._is_blacklisted_address(event.chain_id, event.from_address)
        to_blacklisted = self._is_blacklisted_address(event.chain_id, event.to_address)
        
        # Get chain info for alert context
        chain_name = self._get_chain_name(event.chain_id)
        
        # 1. Check for blacklisted addresses
        if from_blacklisted or to_blacklisted:
            alert_key = f"blacklist:{event.chain_id}:{event.from_address}:{event.to_address}"
            
            if self._should_alert(alert_key):
                blacklisted_addresses = []
                if from_blacklisted:
                    blacklisted_addresses.append(event.from_address)
                if to_blacklisted:
                    blacklisted_addresses.append(event.to_address)
                    
                alerts.append(Alert(
                    title="Blacklisted Address Activity",
                    description=f"Transfer involving blacklisted address(es): {', '.join(blacklisted_addresses)}",
                    severity="high",
                    source="token_movement_strategy",
                    timestamp=event.block_timestamp,
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
                        "blacklisted_addresses": blacklisted_addresses
                    }
                ))
        
        # 2. Check for significant transfers
        if self._is_significant_transfer(event):
            alert_key = f"significant:{event.chain_id}:{event.token_symbol or 'native'}"
            
            # Always alert for watched addresses
            from_watched = self._is_watched_address(event.chain_id, event.from_address)
            to_watched = self._is_watched_address(event.chain_id, event.to_address)
            
            if self._should_alert(alert_key) or from_watched or to_watched:
                alerts.append(Alert(
                    title="Significant Token Transfer",
                    description=f"Large transfer of {event.formatted_value} {event.token_symbol or 'native tokens'} detected",
                    severity="medium",
                    source="token_movement_strategy",
                    timestamp=event.block_timestamp,
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
                        "from_watched": from_watched,
                        "to_watched": to_watched
                    }
                ))
        
        # 3. Check for unusual transfers based on historical data
        if self._is_unusual_transfer(event):
            alert_key = f"unusual:{event.chain_id}:{event.token_symbol or 'native'}"
            
            if self._should_alert(alert_key):
                token_key = (event.chain_id, event.token_address or 'native')
                stats = self.token_stats.get(token_key, {})
                mean_value = stats.get('mean_value', 0)
                stdev_value = stats.get('stdev_value', 0)
                
                # Calculate how unusual this transfer is
                if stdev_value > 0:
                    z_score = (event.formatted_value - mean_value) / stdev_value
                    magnitude = f"{z_score:.2f} standard deviations from mean"
                else:
                    magnitude = f"{event.formatted_value / mean_value:.2f}x average transfer size"
                
                alerts.append(Alert(
                    title="Unusual Token Transfer",
                    description=f"Transfer of {event.formatted_value} {event.token_symbol or 'native tokens'} is {magnitude}",
                    severity="medium",
                    source="token_movement_strategy",
                    timestamp=event.block_timestamp,
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
                        "magnitude": magnitude
                    }
                ))
        
        # 4. Check for sudden activity from dormant address
        address_key = (event.chain_id, event.from_address)
        address_stats = self.address_stats.get(address_key, {})
        
        if 'first_seen' in address_stats and 'last_seen' in address_stats:
            first_seen = address_stats['first_seen']
            last_seen = address_stats.get('last_active', first_seen)
            current_time = event.block_timestamp
            
            # Address considered dormant if inactive for over 30 days
            dormant_threshold = timedelta(days=30)
            dormant_period = current_time - last_seen
            
            if dormant_period > dormant_threshold:
                alert_key = f"dormant:{event.chain_id}:{event.from_address}"
                
                if self._should_alert(alert_key):
                    alerts.append(Alert(
                        title="Dormant Address Activity",
                        description=f"Address {event.from_address} active after {dormant_period.days} days of inactivity",
                        severity="medium",
                        source="token_movement_strategy",
                        timestamp=event.block_timestamp,
                        data={
                            "chain_id": event.chain_id,
                            "chain_name": chain_name,
                            "from_address": event.from_address,
                            "dormant_days": dormant_period.days,
                            "first_seen": first_seen.isoformat(),
                            "last_seen": last_seen.isoformat(),
                            "transaction_hash": event.transaction_hash
                        }
                    ))
        
        # 5. Check for funds being split across multiple addresses in short time period
        # This requires maintaining state of recent transfers from this address
        address_transfers = self.transfers_by_address.get(address_key, [])
        
        # Look at recent transfers from this address (last 24 hours)
        recent_time = event.block_timestamp - timedelta(hours=24)
        recent_transfers = [
            t for t in address_transfers 
            if t.block_timestamp >= recent_time and t.from_address == event.from_address
        ]
        
        # If we have multiple outgoing transfers in a short period, analyze the pattern
        if len(recent_transfers) >= 3:
            # Detect splitting pattern (one address sending to multiple recipients)
            recipients = set(t.to_address for t in recent_transfers)
            
            # If transfers going to multiple destinations
            if len(recipients) >= 3:
                alert_key = f"split:{event.chain_id}:{event.from_address}"
                
                if self._should_alert(alert_key):
                    # Calculate total value transferred
                    total_value = sum(t.formatted_value for t in recent_transfers)
                    
                    alerts.append(Alert(
                        title="Potential Fund Splitting Detected",
                        description=f"Address {event.from_address} sent funds to {len(recipients)} different addresses within 24 hours",
                        severity="medium",
                        source="token_movement_strategy",
                        timestamp=event.block_timestamp,
                        data={
                            "chain_id": event.chain_id,
                            "chain_name": chain_name,
                            "from_address": event.from_address,
                            "recipient_count": len(recipients),
                            "transfer_count": len(recent_transfers),
                            "total_value_transferred": total_value,
                            "token_symbol": event.token_symbol,
                            "time_span_hours": 24
                        }
                    ))
        
        # 6. Check for layered transfers (multiple hops in short time)
        # This is a more complex pattern that requires looking at chains of transfers
        # We implement a simplified version here
        if event.from_address in [t.to_address for t in recent_transfers if t.block_timestamp >= event.block_timestamp - timedelta(minutes=30)]:
            alert_key = f"hop:{event.chain_id}:{event.from_address}:{event.to_address}"
            
            if self._should_alert(alert_key):
                alerts.append(Alert(
                    title="Sequential Transfer Detected",
                    description=f"Address {event.from_address} quickly forwarded received funds",
                    severity="medium",
                    source="token_movement_strategy",
                    timestamp=event.block_timestamp,
                    data={
                        "chain_id": event.chain_id,
                        "chain_name": chain_name,
                        "from_address": event.from_address,
                        "to_address": event.to_address,
                        "value": str(event.value),
                        "formatted_value": event.formatted_value,
                        "token_symbol": event.token_symbol,
                        "transaction_hash": event.transaction_hash
                    }
                ))
        
        return alerts
    
    async def _generate_report(self):
        """Generate a report of token movement statistics"""
        if not self.daily_report:
            return
            
        # Get current time
        now = datetime.now()
        
        # Check if it's time for a report (daily)
        if (now - self.last_report_time).total_seconds() < 86400:  # 24 hours
            return
            
        logger.info("Generating token movement report")
        
        # Statistics cutoff time
        cutoff_time = now - timedelta(hours=self.statistics_window)
        
        # Generate token statistics
        token_report = []
        for (chain_id, token_address), stats in self.token_stats.items():
            # Skip tokens not seen in the statistics window
            if stats['last_seen'] < cutoff_time:
                continue
                
            token_symbol = None
            token_name = None
            
            # Find a recent transfer to get token details
            recent_transfers = self.transfers_by_token.get((chain_id, token_address), [])
            if recent_transfers:
                last_transfer = recent_transfers[-1]
                token_symbol = last_transfer.token_symbol
                token_name = last_transfer.token_name
            
            token_report.append({
                'chain_id': chain_id,
                'token_address': token_address if token_address != 'native' else None,
                'token_symbol': token_symbol,
                'token_name': token_name,
                'total_transfers': stats['transfer_count'],
                'total_volume': stats['total_volume'],
                'largest_transfer': stats['max_transfer'],
                'unique_senders': len(stats['interacted_with']),
                'unique_receivers': len(stats['interacted_with']),
            })
            
        # Generate address statistics for most active addresses
        address_report = []
        sorted_addresses = sorted(
            self.address_stats.items(),
            key=lambda x: x[1]['total_sent'] + x[1]['total_received'],
            reverse=True
        )
        
        # Take top 100 addresses by volume
        for (chain_id, address), stats in sorted_addresses[:100]:
            # Skip addresses not seen in the statistics window
            if stats['last_seen'] < cutoff_time:
                continue
                
            address_report.append({
                'chain_id': chain_id,
                'address': address,
                'sent_count': stats['sent_count'],
                'received_count': stats['received_count'],
                'sent_volume': stats['total_sent'],
                'received_volume': stats['total_received'],
                'unique_tokens_sent': len(stats['tokens_transferred']),
                'unique_tokens_received': len(stats['tokens_transferred']),
            })
        
        # Create report alert
        report = {
            'generated_at': now.isoformat(),
            'time_window_hours': self.statistics_window,
            'tokens': token_report,
            'addresses': address_report,
        }
        
        report_alert = Alert(
            title="Token Movement Daily Report",
            description=f"Daily report of token movement statistics over the past {self.statistics_window} hours",
            severity="info",
            source="token_movement_strategy",
            timestamp=now,
            data=report
        )
        
        # Update last report time
        self.last_report_time = now
        
        # Return the report alert
        return report_alert
    
    async def process_event(self, event: Event) -> List[Any]:
        """
        Process event and generate actions
        
        This method is required by the Strategy abstract base class.
        It delegates to the analyze method which handles the actual event analysis.
        
        Args:
            event: Event to process
            
        Returns:
            List[Any]: List of actions generated from this event
        """
        # Call analyze to handle the event and generate alerts
        alerts = await self.analyze(event)
        
        # Convert alerts to actions (in this strategy, the actions are just the alerts)
        # If additional action types are needed, they can be added here
        return alerts
        
    async def analyze(self, event: Event) -> List[Alert]:
        """
        Analyze token transfer events and generate alerts
        
        This method represents the core logic of the token movement strategy:
        1. Filter events to focus only on token transfers of interest
        2. Update statistical models with new data
        3. Apply pattern detection algorithms to identify unusual activity
        4. Generate appropriate alerts based on the findings
        5. Periodically create summary reports of token movements
        
        Args:
            event: Event to analyze
            
        Returns:
            List[Alert]: Alerts generated
        """
        # Check if this is a token transfer event
        if not isinstance(event, TokenTransferEvent):
            return []
        
        # Initialize alert list
        alerts = []
        
        # Always update statistics to maintain historical data
        self._update_statistics(event)
        
        # Get chain info for alert context
        chain_name = self._get_chain_name(event.chain_id)
        
        # Check if addresses involved are being watched
        from_watched = self._is_watched_address(event.chain_id, event.from_address)
        to_watched = self._is_watched_address(event.chain_id, event.to_address)
        
        # Check if the token is being watched
        token_watched = self._is_watched_token(event.chain_id, event.token_address)
        
        # Check if the transfer is significant based on value
        is_significant = self._is_significant_transfer(event)
        
        # Check if the transfer is unusual based on historical data
        is_unusual = self._is_unusual_transfer(event)
        
        # Generate alerts based on our findings
        
        # 1. Alert for significant transfers
        if is_significant or from_watched or to_watched or token_watched:
            # Create a unique key for this type of alert to prevent spam
            alert_key = f"significant_transfer:{event.chain_id}:{event.token_address}:{event.transaction_hash}"
            
            if self._should_alert(alert_key):
                # Create alert for significant transfer
                alert = Alert(
                    title=f"Significant Token Transfer: {event.formatted_value} {event.token_symbol}",
                    description=f"A significant transfer of {event.formatted_value} {event.token_symbol} "
                                f"occurred from {event.from_address} to {event.to_address} "
                                f"on {chain_name}.",
                    severity="medium",
                    source="token_movement_strategy",
                    timestamp=event.block_timestamp,
                    data={
                        "chain_id": event.chain_id,
                        "chain_name": chain_name,
                        "token_address": event.token_address,
                        "token_symbol": event.token_symbol,
                        "token_name": event.token_name,
                        "from_address": event.from_address,
                        "to_address": event.to_address,
                        "value": event.value,
                        "formatted_value": event.formatted_value,
                        "transaction_hash": event.transaction_hash,
                        "block_number": event.block_number,
                        "block_timestamp": event.block_timestamp.isoformat() if event.block_timestamp else None,
                        "is_significant": is_significant,
                        "is_unusual": is_unusual,
                        "from_watched": from_watched,
                        "to_watched": to_watched,
                        "token_watched": token_watched
                    }
                )
                alerts.append(alert)
        
        # 2. Alert for unusual transfers
        if is_unusual:
            # Create a unique key for this type of alert to prevent spam
            alert_key = f"unusual_transfer:{event.chain_id}:{event.token_address}:{event.transaction_hash}"
            
            if self._should_alert(alert_key):
                # Get token stats for context
                token_key = (event.chain_id, event.token_address or 'native')
                stats = self.token_stats.get(token_key, {})
                
                avg_transfer = stats.get('avg_transfer', 0)
                times_larger = "N/A"
                if avg_transfer > 0:
                    times_larger = f"{event.formatted_value / avg_transfer:.2f}x"
                
                # Create alert for unusual transfer
                alert = Alert(
                    title=f"Unusual Token Transfer: {event.formatted_value} {event.token_symbol}",
                    description=f"An unusual transfer of {event.formatted_value} {event.token_symbol} "
                                f"({times_larger} larger than average transfer size) "
                                f"occurred from {event.from_address} to {event.to_address} "
                                f"on {chain_name}. This is significantly above standard deviations.",
                    severity="medium",
                    source="token_movement_strategy",
                    timestamp=event.block_timestamp,
                    data={
                        "chain_id": event.chain_id,
                        "chain_name": chain_name,
                        "token_address": event.token_address,
                        "token_symbol": event.token_symbol,
                        "token_name": event.token_name,
                        "from_address": event.from_address,
                        "to_address": event.to_address,
                        "value": event.value,
                        "formatted_value": event.formatted_value,
                        "transaction_hash": event.transaction_hash,
                        "block_number": event.block_number,
                        "block_timestamp": event.block_timestamp.isoformat() if event.block_timestamp else None,
                        "avg_transfer": avg_transfer,
                        "times_larger": times_larger
                    }
                )
                alerts.append(alert)
        
        # Check for additional unusual patterns
        pattern_alerts = await self._check_for_unusual_patterns(event)
        alerts.extend(pattern_alerts)
        
        # Generate daily report if needed
        if self.daily_report:
            now = datetime.now()
            if (now - self.last_report_time).total_seconds() > 86400:  # 24 hours
                report_alert = await self._generate_report()
                if report_alert:
                    alerts.append(report_alert)
                self.last_report_time = now
        
        return alerts 