"""
Logging configuration for Sentinel

Provides:
- Console and file logging
- Log rotation
- Configurable log levels
- Structured log format
"""

import sys
from typing import Any, Dict

from loguru import logger

# 配置日志格式
LOG_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"

# 移除默认的 handler 并添加一个基础的控制台 handler
logger.remove()
logger.add(sys.stderr, format=LOG_FORMAT, level="INFO", enqueue=True)


def setup_logger(config: Dict[str, Any] = None) -> None:
    """
    设置日志配置

    Args:
        config: 日志配置字典,包含:
            - level: 日志级别
            - file: 日志文件路径
            - rotation: 日志轮转配置
            - retention: 日志保留时间
    """
    if not config:
        return  # 如果没有配置，使用默认的控制台输出

    # 移除之前的所有 handler
    logger.remove()

    # 添加新的控制台输出
    logger.add(
        sys.stderr, format=LOG_FORMAT, level=config.get("level", "INFO"), enqueue=True
    )

    # 如果配置了文件日志
    if log_file := config.get("file"):
        logger.add(
            log_file,
            format=LOG_FORMAT,
            level=config.get("level", "INFO"),
            rotation=config.get("rotation", "500 MB"),
            retention=config.get("retention", "7 days"),
            compression="zip",
            enqueue=True,
        )
