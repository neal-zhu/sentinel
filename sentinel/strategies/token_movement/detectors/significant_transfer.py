"""
Significant transfer detector for the Token Movement Strategy.
"""
from datetime import datetime
from typing import Any, Dict, List

from sentinel.core.alerts import Alert
from sentinel.core.events import TokenTransferEvent
from sentinel.logger import logger
from sentinel.strategies.token_movement.detectors.base import BaseDetector
from sentinel.strategies.token_movement.utils.chain_info import ChainInfo
from sentinel.strategies.token_movement.utils.token_utils import TokenUtils


class SignificantTransferDetector(BaseDetector):
    """
    Detector for significant token transfers.

    This detector identifies transfers that exceed configured thresholds,
    which may indicate important movements of funds.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the significant transfer detector.

        Args:
            config: Configuration parameters for the detector
        """
        super().__init__(config)
        self.significant_transfer_threshold = self.config.get(
            "significant_transfer_threshold", {}
        )
        self.default_threshold = self.config.get("default_threshold", 100.0)
        self.stablecoin_threshold = self.config.get("stablecoin_threshold", 5000.0)

    def is_significant_transfer(
        self, event: TokenTransferEvent, context: Dict[str, Any]
    ) -> bool:
        """
        Determine if a transfer is significant based on configured thresholds.

        Args:
            event: Token transfer event
            context: Additional context information

        Returns:
            bool: Whether this is a significant transfer
        """
        # If it involves a contract interaction, it's more likely to be significant
        if event.has_contract_interaction:
            # Contract interactions are typically more significant, use a lower threshold
            threshold_multiplier = 0.5  # 50% of the normal threshold
        else:
            threshold_multiplier = 1.0

        # Check thresholds by chain and token
        chain_str = str(event.chain_id)

        # If no thresholds for this chain, use default logic
        if chain_str not in self.significant_transfer_threshold:
            # Stablecoins typically have higher thresholds
            if TokenUtils.is_stablecoin(
                event.chain_id, event.token_address or "", event.token_symbol
            ):
                return event.formatted_value >= (
                    self.stablecoin_threshold * threshold_multiplier
                )
            else:
                return event.formatted_value >= (
                    self.default_threshold * threshold_multiplier
                )

        # Get thresholds for this chain
        chain_thresholds = self.significant_transfer_threshold[chain_str]

        # If no threshold for this token, use a default if available
        if event.token_symbol not in chain_thresholds:
            if "DEFAULT" in chain_thresholds:
                threshold = chain_thresholds["DEFAULT"]
            else:
                # No default threshold, use stablecoin logic
                if TokenUtils.is_stablecoin(
                    event.chain_id, event.token_address or "", event.token_symbol
                ):
                    return event.formatted_value >= (
                        self.stablecoin_threshold * threshold_multiplier
                    )
                else:
                    return event.formatted_value >= (
                        self.default_threshold * threshold_multiplier
                    )
        else:
            threshold = chain_thresholds[event.token_symbol]

        return event.formatted_value >= (threshold * threshold_multiplier)

    async def detect(
        self, event: TokenTransferEvent, context: Dict[str, Any]
    ) -> List[Alert]:
        """
        Detect significant transfers and generate alerts.

        Args:
            event: The token transfer event to analyze
            context: Additional context information

        Returns:
            List[Alert]: List of alerts generated, if any
        """
        alerts = []

        # Check if this is a significant transfer
        is_significant = self.is_significant_transfer(event, context)

        # Update context with this information for other components
        context["is_significant_transfer"] = is_significant

        if is_significant:
            # Add contract interaction information to the alert title and description
            contract_info = ""
            if event.has_contract_interaction:
                contract_info = " with contract interaction"

            logger.info(
                f"Significant transfer{contract_info} detected: {event.formatted_value} {event.token_symbol or 'native tokens'}"
            )

            alerts.append(
                Alert(
                    title=f"Significant Token Transfer{contract_info}",
                    description=f"Large transfer of {event.formatted_value} {event.token_symbol or 'native tokens'} detected{contract_info}",
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
                        "value": str(event.value),
                        "formatted_value": event.formatted_value,
                        "transaction_hash": event.transaction_hash,
                        "block_number": event.block_number,
                        "has_contract_interaction": event.has_contract_interaction,
                    },
                )
            )

        return alerts
