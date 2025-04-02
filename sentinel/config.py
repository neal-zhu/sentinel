from pathlib import Path
from typing import Any, Dict, Optional

import tomli

from sentinel.logger import logger


class Config:
    """
    Configuration manager for Sentinel

    Handles loading and accessing configuration from TOML files.
    Provides default values and graceful error handling.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager

        Args:
            config_path: Path to the TOML configuration file.
                        If not provided, defaults to "config.toml"
        """
        self.config_path = config_path or "config.toml"
        self.config: Dict[str, Any] = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from TOML file

        Returns:
            Dict[str, Any]: Configuration dictionary, empty if file not found or invalid
        """
        config_path = Path(self.config_path)
        if not config_path.exists():
            logger.warning(
                f"Config file not found: {self.config_path}, using empty configuration"
            )
            return {}

        try:
            with open(config_path, "rb") as f:
                return tomli.load(f)
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-separated key

        Args:
            key: Dot-separated configuration key (e.g., "collectors.web3.url")
            default: Default value if key not found

        Returns:
            Any: Configuration value or default if not found
        """
        try:
            value = self.config
            for k in key.split("."):
                if not isinstance(value, dict):
                    return default
                value = value.get(k, default)
            return value if value is not None else default
        except Exception as e:
            logger.error(f"Error getting config value for key '{key}': {e}")
            return default

    @property
    def collectors(self) -> list:
        """Get list of enabled collectors"""
        return self.config.get("collectors", {}).get("enabled", [])

    @property
    def strategies(self) -> list:
        """Get list of enabled strategies"""
        return self.config.get("strategies", {}).get("enabled", [])

    @property
    def executors(self) -> list:
        """Get list of enabled executors"""
        return self.config.get("executors", {}).get("enabled", [])

    def get_collector_config(self, collector_name: str) -> dict:
        """
        Get configuration for specific collector

        Args:
            collector_name: Name of the collector

        Returns:
            dict: Collector configuration or empty dict if not found
        """
        return self.config.get("collectors", {}).get(collector_name, {})

    def get_strategy_config(self, strategy_name: str) -> dict:
        """
        Get configuration for specific strategy

        Args:
            strategy_name: Name of the strategy

        Returns:
            dict: Strategy configuration or empty dict if not found
        """
        return self.config.get("strategies", {}).get(strategy_name, {})

    def get_executor_config(self, executor_name: str) -> dict:
        """
        Get configuration for specific executor

        Args:
            executor_name: Name of the executor

        Returns:
            dict: Executor configuration or empty dict if not found
        """
        return self.config.get("executors", {}).get(executor_name, {})
