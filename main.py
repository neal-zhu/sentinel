import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional

# Import sentinel package which automatically registers all components
import sentinel
from sentinel.config import Config
from sentinel.core.builder import SentinelBuilder
from sentinel.logger import logger, setup_logger

class GracefulExit(SystemExit):
    """Custom exception for handling graceful shutdown"""
    code = 1

def handle_signal(signum, frame):
    """
    Signal handler for graceful shutdown
    
    Args:
        signum: Signal number received
        frame: Current stack frame
    """
    logger.info(f"Received signal {signum}")
    raise GracefulExit()

async def run_sentinel(config_path: Optional[str] = None) -> None:
    """
    Main function to run the Sentinel application
    
    Args:
        config_path: Optional path to the configuration file
    """
    sentinel_instance = None
    
    try:
        # Initialize configuration
        config = Config(config_path)
        
        # Setup logging based on configuration
        setup_logger(config.get('logging', {}))
        
        # Build Sentinel instance using builder pattern
        sentinel_instance = (SentinelBuilder(config)
                          .build_collectors()
                          .build_strategies()
                          .build_executors()
                          .build())
        
        # Start and run the instance
        logger.info("Starting Sentinel...")
        await sentinel_instance.start()
        
        # Wait for shutdown signal
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
                # Attempt to stop all components with timeout
                await asyncio.wait_for(sentinel_instance.stop(), timeout=10.0)
                logger.info("Sentinel stopped successfully")
            except asyncio.TimeoutError:
                logger.error("Timeout while stopping Sentinel")
            except Exception as e:
                logger.error(f"Error stopping Sentinel: {e}")

def main():
    """
    Entry point for the command line interface
    
    Handles:
    1. Signal registration for graceful shutdown
    2. Configuration file loading
    3. Main application execution
    4. Error handling and exit codes
    """
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # Handle configuration file path from command line
    config_path = None
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
        if not config_path.exists():
            logger.error(f"Config file not found: {config_path}")
            sys.exit(1)
    
    try:
        # Run the main application
        asyncio.run(run_sentinel(config_path))
    except GracefulExit:
        # Normal shutdown
        sys.exit(0)
    except Exception as e:
        # Fatal error
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()