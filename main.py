import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional

# 导入 artemis 包会自动注册所有组件
import sentinel
from sentinel.config import Config
from sentinel.core.builder import SentinelBuilder
from sentinel.logger import logger, setup_logger

class GracefulExit(SystemExit):
    code = 1

def handle_signal(signum, frame):
    """处理退出信号"""
    logger.info(f"Received signal {signum}")
    raise GracefulExit()

async def run_sentinel(config_path: Optional[str] = None) -> None:
    """运行 Sentinel"""
    sentinel_instance = None
    
    try:
        # 初始化配置
        config = Config(config_path)
        
        # 设置日志配置
        setup_logger(config.get('logging', {}))
        
        # 使用构建器创建实例
        sentinel_instance = (SentinelBuilder(config)
                          .build_collectors()
                          .build_strategies()
                          .build_executors()
                          .build())
        
        # 启动并运行
        logger.info("Starting Sentinel...")
        await sentinel_instance.start()
        
        # 等待退出信号
        try:
            await sentinel_instance.join()
        except GracefulExit:
            logger.info("Received shutdown signal, stopping gracefully...")
        
    except Exception as e:
        import traceback
        logger.error(f"Error running Sentinel: {e}")
        logger.error(traceback.format_exc())
        raise
    finally:
        if sentinel_instance:
            logger.info("Shutting down Sentinel...")
            try:
                await asyncio.wait_for(sentinel_instance.stop(), timeout=10.0)
                logger.info("Sentinel stopped successfully")
            except asyncio.TimeoutError:
                logger.error("Timeout while stopping Sentinel")
            except Exception as e:
                logger.error(f"Error stopping Sentinel: {e}")

def main():
    """命令行入口点"""
    # 注册信号处理器
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    config_path = None
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
        if not config_path.exists():
            logger.error(f"Config file not found: {config_path}")
            sys.exit(1)
    
    try:
        asyncio.run(run_sentinel(config_path))
    except GracefulExit:
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()