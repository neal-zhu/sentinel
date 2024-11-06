from pathlib import Path
import tomli
from typing import Any, Dict, Optional

class Config:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config.toml"
        self.config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> None:
        """Load configuration from TOML file"""
        config_path = Path(self.config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        with open(config_path, "rb") as f:
            self.config = tomli.load(f)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    @property
    def collectors(self) -> list:
        """Get enabled collectors"""
        return self.config.get('collectors', {}).get('enabled', [])

    @property
    def strategies(self) -> list:
        """Get enabled strategies"""
        return self.config.get('strategies', {}).get('enabled', [])

    @property
    def executors(self) -> list:
        """Get enabled executors"""
        return self.config.get('executors', {}).get('enabled', [])

    def get_collector_config(self, collector_name: str) -> dict:
        """Get configuration for specific collector"""
        return self.config.get('collectors', {}).get(collector_name, {})

    def get_strategy_config(self, strategy_name: str) -> dict:
        """Get configuration for specific strategy"""
        return self.config.get('strategies', {}).get(strategy_name, {})

    def get_executor_config(self, executor_name: str) -> dict:
        """Get configuration for specific executor"""
        return self.config.get('executors', {}).get(executor_name, {})
