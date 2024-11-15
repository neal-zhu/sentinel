from pathlib import Path
import tomli
from typing import Any, Dict, Optional
from sentinel.logger import logger

class Config:
    def __init__(self, config_path: Optional[str] = None):
        """初始化配置"""
        self.config_path = config_path or "config.toml"
        self.config: Dict[str, Any] = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        config_path = Path(self.config_path)
        if not config_path.exists():
            logger.warning(f"Config file not found: {self.config_path}, using empty configuration")
            return {}
        
        try:
            with open(config_path, "rb") as f:
                return tomli.load(f)
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        try:
            value = self.config
            for k in key.split('.'):
                if not isinstance(value, dict):
                    return default
                value = value.get(k, default)
            return value if value is not None else default
        except Exception as e:
            logger.error(f"Error getting config value for key '{key}': {e}")
            return default

    @property
    def collectors(self) -> list:
        """获取启用的收集器列表"""
        return self.config.get('collectors', {}).get('enabled', [])

    @property
    def strategies(self) -> list:
        """获取启用的策略列表"""
        return self.config.get('strategies', {}).get('enabled', [])

    @property
    def executors(self) -> list:
        """获取启用的执行器列表"""
        return self.config.get('executors', {}).get('enabled', [])

    def get_collector_config(self, collector_name: str) -> dict:
        """获取特定收集器的配置"""
        return self.config.get('collectors', {}).get(collector_name, {})

    def get_strategy_config(self, strategy_name: str) -> dict:
        """获取特定策略的配置"""
        return self.config.get('strategies', {}).get(strategy_name, {})

    def get_executor_config(self, executor_name: str) -> dict:
        """获取特定执行器的配置"""
        return self.config.get('executors', {}).get(executor_name, {})
