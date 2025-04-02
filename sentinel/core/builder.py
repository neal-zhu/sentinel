from typing import List

from ..config import Config
from ..logger import logger
from .base import Collector, Executor, Strategy
from .sentinel import Sentinel


class SentinelBuilder:
    """Sentinel构建器"""

    def __init__(self, config: Config):
        self.config = config

        # 获取队列配置，但只使用 group_name 和 stats_interval
        queue_config = config.get("queues", {})
        group_name = queue_config.get("group_name", "sentinel")
        stats_interval = queue_config.get("stats_interval", 60)

        # 使用新的初始化参数创建 Sentinel 实例
        self.sentinel = Sentinel(
            group_name=group_name,
            stats_interval=stats_interval,
        )

        self.collectors: List[Collector] = []
        self.strategies: List[Strategy] = []
        self.executors: List[Executor] = []

    def build_collectors(self) -> "SentinelBuilder":
        """构建所有启用的收集器"""
        collectors = self.config.collectors
        if not isinstance(collectors, list):
            raise ValueError("enabled_collectors must be a list")

        for name in collectors:
            collector = Collector.create(
                name, **self.config.get(f"collectors.{name}", {})
            )
            self.collectors.append(collector)
            logger.info(f"Added collector: {name}")
        return self

    def build_strategies(self) -> "SentinelBuilder":
        """构建所有启用的策略"""
        strategies = self.config.strategies
        if not isinstance(strategies, list):
            raise ValueError("enabled_strategies must be a list")

        for name in strategies:
            strategy = Strategy.create(
                name, **self.config.get(f"strategies.{name}", {})
            )
            self.strategies.append(strategy)
            logger.info(f"Added strategy: {name}")
        return self

    def build_executors(self) -> "SentinelBuilder":
        """构建所有启用的执行器"""
        executors = self.config.executors
        if not isinstance(executors, list):
            raise ValueError("enabled_executors must be a list")

        for name in executors:
            executor = Executor.create(name, **self.config.get(f"executors.{name}", {}))
            self.executors.append(executor)
            logger.info(f"Added executor: {name}")
        return self

    def build(self) -> Sentinel:
        """构建最终的 Sentinel 实例"""
        # 添加所有组件
        for collector in self.collectors:
            self.sentinel.add_collector(collector)

        for strategy in self.strategies:
            self.sentinel.add_strategy(strategy)

        for executor in self.executors:
            self.sentinel.add_executor(executor)

        return self.sentinel
