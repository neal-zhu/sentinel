"""
Token Movement Strategy Package

This package contains a modular implementation of the Token Movement Strategy,
which analyzes token transfer events to detect various patterns and anomalies.

The strategy is implemented using a plugin architecture, with detectors and filters
that can be enabled or disabled as needed.
"""

from sentinel.strategies.token_movement.core.strategy import TokenMovementStrategy

__all__ = ['TokenMovementStrategy']
