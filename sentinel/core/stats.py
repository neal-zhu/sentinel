import asyncio
import time
from typing import Callable, Optional
from ..logger import logger


class StatsManager:
    """
    Manages performance statistics and metrics for Sentinel components
    
    Handles:
    - Tracking event and action counts
    - Calculating throughput rates
    - Monitoring component idle times
    - Periodic stats logging
    """
    
    def __init__(
        self,
        stats_interval: int = 60,  # Log stats every minute
        get_collector_queue_size: Optional[Callable[[], int]] = None,
        get_executor_queue_size: Optional[Callable[[], int]] = None
    ):
        """
        Initialize stats manager
        
        Args:
            stats_interval: How often to log statistics (in seconds)
            get_collector_queue_size: Function to get collector queue size
            get_executor_queue_size: Function to get executor queue size
        """
        self.stats_interval = stats_interval
        self.get_collector_queue_size = get_collector_queue_size
        self.get_executor_queue_size = get_executor_queue_size
        
        # Performance metrics
        self.events_collected = 0
        self.events_processed = 0
        self.actions_generated = 0
        self.actions_executed = 0
        self.last_stats_time = time.time()
        
        # Component status
        self.collector_idle_time = 0
        self.strategy_idle_time = 0
        self.executor_idle_time = 0
        self.last_collector_active = time.time()
        self.last_strategy_active = time.time()
        self.last_executor_active = time.time()
        
        self.running = False
        self._task = None

    def on_event_collected(self):
        """Record event collection"""
        self.events_collected += 1
        self.last_collector_active = time.time()
        
    def on_event_processed(self):
        """Record event processing"""
        self.events_processed += 1
        self.last_strategy_active = time.time()
        
    def on_action_generated(self):
        """Record action generation"""
        self.actions_generated += 1
        
    def on_action_executed(self):
        """Record action execution"""
        self.actions_executed += 1
        self.last_executor_active = time.time()
    
    async def start(self):
        """Start the stats logging task"""
        self.running = True
        self._task = asyncio.create_task(
            self._log_stats(), 
            name="stats_manager"
        )
        return self._task
    
    async def stop(self):
        """Stop the stats logging task"""
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        # Log final stats
        logger.info(
            f"Final stats - Events: collected={self.events_collected}, processed={self.events_processed}, "
            f"Actions: generated={self.actions_generated}, executed={self.actions_executed}"
        )
    
    async def _log_stats(self):
        """Log periodic statistics"""
        while self.running:
            try:
                now = time.time()
                elapsed = now - self.last_stats_time
                
                # Calculate rates
                event_collect_rate = self.events_collected / elapsed if elapsed > 0 else 0
                event_process_rate = self.events_processed / elapsed if elapsed > 0 else 0
                action_gen_rate = self.actions_generated / elapsed if elapsed > 0 else 0
                action_exec_rate = self.actions_executed / elapsed if elapsed > 0 else 0
                
                # Get queue sizes
                events_queued = self.get_collector_queue_size() if self.get_collector_queue_size else 0
                actions_queued = self.get_executor_queue_size() if self.get_executor_queue_size else 0
                
                # Calculate idle times
                collector_idle = now - self.last_collector_active
                strategy_idle = now - self.last_strategy_active
                executor_idle = now - self.last_executor_active
                
                # Log stats
                logger.info(
                    f"Stats - Events: collected={self.events_collected} ({event_collect_rate:.1f}/s), "
                    f"processed={self.events_processed} ({event_process_rate:.1f}/s), queued={events_queued} | "
                    f"Actions: generated={self.actions_generated} ({action_gen_rate:.1f}/s), "
                    f"executed={self.actions_executed} ({action_exec_rate:.1f}/s), queued={actions_queued} | "
                    f"Idle times: collector={collector_idle:.1f}s, strategy={strategy_idle:.1f}s, executor={executor_idle:.1f}s"
                )
                
                # Log component status if idle for too long
                if collector_idle > 60:  # 1 minute
                    logger.warning(f"Collector has been idle for {collector_idle:.1f} seconds")
                if strategy_idle > 60:
                    logger.warning(f"Strategy processor has been idle for {strategy_idle:.1f} seconds")
                if executor_idle > 60:
                    logger.warning(f"Action executor has been idle for {executor_idle:.1f} seconds")
                
                # Reset counters
                self.events_collected = 0
                self.events_processed = 0
                self.actions_generated = 0
                self.actions_executed = 0
                self.last_stats_time = now
                
            except Exception as e:
                logger.error(f"Error logging stats: {e}")
                
            await asyncio.sleep(int(self.stats_interval)) 