"""
Periodic transfer detector for the Token Movement Strategy.
"""
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sentinel.core.alerts import Alert
from sentinel.core.events import TokenTransferEvent
from sentinel.logger import logger
from sentinel.strategies.token_movement.detectors.base import BaseDetector
from sentinel.strategies.token_movement.utils.chain_info import ChainInfo


class PeriodicTransferDetector(BaseDetector):
    """
    Detector for periodic transfer patterns.

    This detector identifies addresses that make transfers at regular intervals,
    which may indicate automated processes like mining rewards, staking rewards,
    or scheduled operations.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the periodic transfer detector.

        Args:
            config: Configuration parameters for the detector
        """
        super().__init__(config)
        self.min_transfers = self.config.get("min_transfers", 4)
        self.max_variation = self.config.get(
            "max_variation", 0.25
        )  # 25% variation allowed
        self.window_days = self.config.get("window_days", 7)

    async def detect(
        self, event: TokenTransferEvent, context: Dict[str, Any]
    ) -> List[Alert]:
        """
        Detect periodic transfer patterns and generate alerts.

        Args:
            event: The token transfer event to analyze
            context: Additional context information

        Returns:
            List[Alert]: List of alerts generated, if any
        """
        alerts = []

        # Get transfers by address from context
        transfers_by_address = context.get("transfers_by_address", {})

        # Only check outgoing transfers (from_address)
        address = event.from_address
        address_key = (event.chain_id, address)

        # Get transfers from this address
        outgoing_transfers = [
            t
            for t in transfers_by_address.get(address_key, [])
            if t.from_address.lower() == address.lower()
        ]

        # Skip if we don't have enough transfers
        if len(outgoing_transfers) < self.min_transfers:
            return []

        # Filter to recent transfers
        recent_time = event.block_timestamp - timedelta(days=self.window_days)
        recent_transfers = [
            t for t in outgoing_transfers if t.block_timestamp >= recent_time
        ]

        # Skip if we don't have enough recent transfers
        if len(recent_transfers) < self.min_transfers:
            return []

        # Sort transfers by timestamp
        sorted_transfers = sorted(recent_transfers, key=lambda t: t.block_timestamp)

        # Calculate intervals between transfers (in blocks)
        intervals = []
        for i in range(1, len(sorted_transfers)):
            prev_block = sorted_transfers[i - 1].block_number
            curr_block = sorted_transfers[i].block_number
            interval = curr_block - prev_block
            if interval > 0:  # Ignore transfers in same block
                intervals.append(interval)

        # Skip if we don't have enough intervals
        if len(intervals) < self.min_transfers - 1:
            return []

        # Calculate statistics
        try:
            avg_interval = statistics.mean(intervals)
            stdev_interval = statistics.stdev(intervals) if len(intervals) > 1 else 0

            # Calculate coefficient of variation (lower means more regular)
            variation = (
                stdev_interval / avg_interval if avg_interval > 0 else float("inf")
            )

            # If variation is low enough, this is a periodic pattern
            if variation <= self.max_variation:
                # Convert blocks to hours for readability
                avg_interval_hours = (
                    ChainInfo.estimate_time_from_blocks(event.chain_id, avg_interval)
                    / 3600
                )

                # Identify tokens involved
                token_addresses = set()
                for t in sorted_transfers:
                    token_addresses.add(t.token_address or "native")

                # Identify frequent recipients
                recipient_counts = defaultdict(int)
                for t in sorted_transfers:
                    recipient_counts[t.to_address.lower()] += 1

                # Recipients that received at least 25% of transfers
                min_count = max(2, len(sorted_transfers) * 0.25)
                frequent_recipients = [
                    addr
                    for addr, count in recipient_counts.items()
                    if count >= min_count
                ]

                # Get token symbols for description
                token_symbols = set()
                for t in sorted_transfers:
                    if t.token_symbol:
                        token_symbols.add(t.token_symbol)
                    elif t.is_native:
                        token_symbols.add(ChainInfo.get_native_symbol(event.chain_id))

                # Format description
                token_info = ""
                if token_symbols:
                    token_info = f" involving {', '.join(token_symbols)}"

                recipient_info = ""
                if frequent_recipients:
                    recipient_info = (
                        f" to {len(frequent_recipients)} frequent recipients"
                    )

                logger.info(
                    f"Periodic transfer pattern detected for address {address}: ~{avg_interval_hours:.1f} hours interval"
                )

                alerts.append(
                    Alert(
                        title="Periodic Transfer Pattern Detected",
                        description=f"Address {address} shows regular transfers{token_info}{recipient_info} every ~{avg_interval_hours:.1f} hours",
                        severity="medium",
                        source="token_movement_strategy",
                        timestamp=datetime.now(),
                        data={
                            "chain_id": event.chain_id,
                            "chain_name": ChainInfo.get_chain_name(event.chain_id),
                            "address": address,
                            "pattern": "periodic_transfers",
                            "avg_interval_blocks": avg_interval,
                            "avg_interval_hours": avg_interval_hours,
                            "transfers_count": len(sorted_transfers),
                            "token_addresses": list(token_addresses),
                            "token_symbols": list(token_symbols),
                            "variation": variation,
                            "frequent_recipients": frequent_recipients,
                            "transaction_hash": event.transaction_hash,
                            "block_number": event.block_number,
                        },
                    )
                )

        except statistics.StatisticsError:
            # Handle error if statistics calculation fails
            pass

        return alerts
