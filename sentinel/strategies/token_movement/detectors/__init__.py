"""
Detector plugins for the Token Movement Strategy.

Detectors are responsible for analyzing token transfer events and identifying
specific patterns or anomalies that may be of interest.
"""

from sentinel.strategies.token_movement.detectors.base import BaseDetector
from sentinel.strategies.token_movement.detectors.continuous_flow import (
    ContinuousFlowDetector,
)
from sentinel.strategies.token_movement.detectors.high_frequency import (
    HighFrequencyDetector,
)
from sentinel.strategies.token_movement.detectors.multi_hop import MultiHopDetector
from sentinel.strategies.token_movement.detectors.periodic_transfer import (
    PeriodicTransferDetector,
)
from sentinel.strategies.token_movement.detectors.significant_transfer import (
    SignificantTransferDetector,
)
from sentinel.strategies.token_movement.detectors.wash_trading import (
    WashTradingDetector,
)

__all__ = [
    "BaseDetector",
    "SignificantTransferDetector",
    "HighFrequencyDetector",
    "ContinuousFlowDetector",
    "PeriodicTransferDetector",
    "MultiHopDetector",
    "WashTradingDetector",
]
