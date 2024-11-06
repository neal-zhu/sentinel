import asyncio
import sys
from pathlib import Path
from typing import Optional

# 导入 artemis 包会自动注册所有组件
import sentinel
from sentinel.config import Config
from sentinel.core.builder import SentinelBuilder
from sentinel.logger import logger

async def run_sentinel(config_path: Optional[str] = None) -> None:
    """运行 Sentinel"""
    try:
        # 初始化配置
        config = Config(config_path)
        
        # 使用构建器创建实例
        sentinel_instance = (SentinelBuilder(config)
                          .build_collectors()
                          .build_strategies()
                          .build_executors()
                          .build())
        
        # 启动并运行
        logger.info("Starting Sentinel...")
        await sentinel_instance.start()
        await sentinel_instance.join()
        
    except KeyboardInterrupt:
        logger.info("Shutting down Sentinel...")
        if 'sentinel_instance' in locals():
            await sentinel_instance.stop()
        
    except Exception as e:
        import traceback
        logger.error(f"Error running Sentinel: {e}")
        logger.error(traceback.format_exc())
        raise

def main():
    """命令行入口点"""
    config_path = None
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
        if not config_path.exists():
            logger.info(f"Config file not found: {config_path}")
            sys.exit(1)
    
    try:
        asyncio.run(run_sentinel(config_path))
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()