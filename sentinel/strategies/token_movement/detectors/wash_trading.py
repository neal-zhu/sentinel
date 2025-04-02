"""
Wash trading detector for the Token Movement Strategy.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sentinel.core.alerts import Alert
from sentinel.core.events import TokenTransferEvent
from sentinel.logger import logger
from sentinel.strategies.token_movement.detectors.base import BaseDetector
from sentinel.strategies.token_movement.utils.chain_info import ChainInfo


class WashTradingDetector(BaseDetector):
    """
    Detector for potential wash trading patterns.

    This detector identifies patterns where tokens are transferred back and forth
    between the same addresses, which may indicate wash trading or other
    market manipulation tactics.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the wash trading detector.

        Args:
            config: Configuration parameters for the detector
        """
        super().__init__(config)
        self.back_and_forth_threshold = self.config.get("back_and_forth_threshold", 3)
        self.window_hours = self.config.get("window_hours", 24)

    async def detect(
        self, event: TokenTransferEvent, context: Dict[str, Any]
    ) -> List[Alert]:
        """
        Detect potential wash trading patterns and generate alerts.

        Args:
            event: The token transfer event to analyze
            context: Additional context information

        Returns:
            List[Alert]: List of alerts generated, if any
        """
        alerts = []

        # Get transfers by address from context
        transfers_by_address = context.get("transfers_by_address", {})

        # Check for transfers back and forth between the same addresses
        from_key = (event.chain_id, event.from_address)
        to_key = (event.chain_id, event.to_address)

        # Get recent transfers from both addresses
        from_transfers = transfers_by_address.get(from_key, [])
        to_transfers = transfers_by_address.get(to_key, [])

        # Look at recent transfers (last window_hours)
        recent_time = event.block_timestamp - timedelta(hours=self.window_hours)

        # Count transfers between these two addresses
        back_and_forth = 0

        for t in from_transfers:
            if (
                t.block_timestamp >= recent_time
                and t.to_address.lower() == event.to_address.lower()
            ):
                back_and_forth += 1

        for t in to_transfers:
            if (
                t.block_timestamp >= recent_time
                and t.to_address.lower() == event.from_address.lower()
            ):
                back_and_forth += 1

        # If we've seen multiple transfers back and forth, this could be wash trading
        if back_and_forth >= self.back_and_forth_threshold:
            logger.info(
                f"Potential wash trading detected: {back_and_forth} transfers back and forth between {event.from_address} and {event.to_address}"
            )

            alerts.append(
                Alert(
                    title="Potential Wash Trading Detected",
                    description=f"Detected {back_and_forth} transfers back and forth between {event.from_address} and {event.to_address} within {self.window_hours} hours",
                    severity="medium",
                    source="token_movement_strategy",
                    timestamp=datetime.now(),
                    data={
                        "chain_id": event.chain_id,
                        "chain_name": ChainInfo.get_chain_name(event.chain_id),
                        "token_symbol": event.token_symbol,
                        "token_address": event.token_address,
                        "from_address": event.from_address,
                        "to_address": event.to_address,
                        "back_and_forth_count": back_and_forth,
                        "window_hours": self.window_hours,
                        "transaction_hash": event.transaction_hash,
                        "block_number": event.block_number,
                    },
                )
            )

        return alerts
