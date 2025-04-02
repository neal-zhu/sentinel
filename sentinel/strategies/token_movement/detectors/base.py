"""
Base detector class for the Token Movement Strategy.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from sentinel.core.alerts import Alert
from sentinel.core.events import TokenTransferEvent


class BaseDetector(ABC):
    """
    Base class for all token movement detectors.

    Detectors are responsible for analyzing token transfer events and identifying
    specific patterns or anomalies that may be of interest.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the detector with configuration parameters.

        Args:
            config: Configuration parameters for the detector
        """
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)

    @abstractmethod
    async def detect(
        self, event: TokenTransferEvent, context: Dict[str, Any]
    ) -> List[Alert]:
        """
        Analyze a token transfer event and generate alerts if a pattern is detected.

        Args:
            event: The token transfer event to analyze
            context: Additional context information from the strategy

        Returns:
            List[Alert]: List of alerts generated, if any
        """
        pass

    def is_enabled(self) -> bool:
        """
        Check if this detector is enabled.

        Returns:
            bool: Whether the detector is enabled
        """
        return self.enabled

    def set_enabled(self, enabled: bool):
        """
        Enable or disable this detector.

        Args:
            enabled: Whether to enable the detector
        """
        self.enabled = enabled
