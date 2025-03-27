import asyncio
import os
import time
from typing import List, Union, Callable, AsyncIterable, Awaitable, Optional
from contextlib import AsyncExitStack
from aiodiskqueue import Queue

from .actions import Action
from .base import (
    Collector, Strategy, Executor,
    FunctionCollector, FunctionStrategy, FunctionExecutor
)
from .events import Event
from ..logger import logger


class Sentinel:
    """
    Main application class that manages the event processing pipeline
    
    Handles:
    - Component lifecycle management
    - Event collection and processing
    - Action execution
    - Error handling and recovery
    """

    def __init__(
        self,
        queue_dir: str = "data/queues",
        group_name: str = "sentinel",
        stats_interval: int = 60,  # Log stats every minute
    ):
        """
        Initialize Sentinel instance
        
        Args:
            queue_dir: Directory for queue storage
            group_name: Group name for queue identification
            stats_interval: How often to log statistics (in seconds)
        """
        self.collectors: List[Collector] = []
        self.strategies: List[Strategy] = []
        self.executors: List[Executor] = []
        self.running = False
        self.stats_interval = stats_interval
        
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
        
        # Ensure queue directory exists
        os.makedirs(queue_dir, exist_ok=True)
        
        # Queue paths
        self.collector_queue_path = os.path.join(queue_dir, f"{group_name}_events.db")
        self.executor_queue_path = os.path.join(queue_dir, f"{group_name}_actions.db")
        
        # Queues will be initialized in start()
        self.collector_queue: Queue[Event] = None  # type: ignore
        self.executor_queue: Queue[Action] = None  # type: ignore
        self._tasks: Optional[List[asyncio.Task]] = None
        self._exit_stack = AsyncExitStack()

    def add_collector(
        self, 
        collector: Union[Collector, Callable[[], AsyncIterable[Event]]]
    ):
        """
        Add event collector to the pipeline
        
        Args:
            collector: Collector instance or async generator function
        """
        if isinstance(collector, Collector):
            self.collectors.append(collector)
        else:
            self.collectors.append(FunctionCollector(collector))
        logger.info(f"Added collector: {collector.__class__.__name__}")

    def add_strategy(
        self, 
        strategy: Union[Strategy, Callable[[Event], Awaitable[List[Action]]]]
    ):
        """
        Add event processing strategy to the pipeline
        
        Args:
            strategy: Strategy instance or async function
        """
        if isinstance(strategy, Strategy):
            self.strategies.append(strategy)
        else:
            self.strategies.append(FunctionStrategy(strategy))
        logger.info(f"Added strategy: {strategy.__class__.__name__}")

    def add_executor(
        self, 
        executor: Union[Executor, Callable[[Action], Awaitable[None]]]
    ):
        """
        Add action executor to the pipeline
        
        Args:
            executor: Executor instance or async function
        """
        if isinstance(executor, Executor):
            self.executors.append(executor)
        else:
            self.executors.append(FunctionExecutor(executor))
        logger.info(f"Added executor: {executor.__class__.__name__}")

    async def start(self):
        """
        Start all components and begin processing
        
        Raises:
            Exception: If any component fails to start
        """
        self.running = True
        
        try:
            # Initialize queues
            self.collector_queue = await Queue.create(self.collector_queue_path)
            self.executor_queue = await Queue.create(self.executor_queue_path)
            
            # Start all collectors
            start_tasks = [collector.start() for collector in self.collectors]
            await asyncio.gather(*start_tasks)
            
            # Create all tasks immediately
            self._tasks = []
            
            # Add collector tasks
            for i, collector in enumerate(self.collectors):
                task = asyncio.create_task(
                    self._run_collector(collector),
                    name=f"collector_{i}"
                )
                self._tasks.append(task)
            
            # Add core tasks
            core_tasks = [
                asyncio.create_task(self._run_strategies(), name="strategies"),
                asyncio.create_task(self._run_executors(), name="executors"),
                asyncio.create_task(self._log_stats(), name="stats")
            ]
            self._tasks.extend(core_tasks)
            
            # Start all tasks concurrently
            await asyncio.gather(*core_tasks, return_exceptions=True)
            
            logger.info(f"Started {len(self.collectors)} collectors, {len(self.strategies)} strategies, {len(self.executors)} executors")
            
        except Exception as e:
            logger.error(f"Error starting components: {e}")
            await self.stop()
            raise

    async def stop(self):
        """
        Stop all components gracefully
        
        Ensures all queued events are processed before shutting down
        """
        self.running = False
        
        try:
            # Stop collectors
            if self.collectors:
                stop_tasks = [collector.stop() for collector in self.collectors]
                await asyncio.gather(*stop_tasks, return_exceptions=True)
            
            # Log final queue sizes
            events_remaining = await self.collector_queue.qsize() if self.collector_queue else 0
            actions_remaining = await self.executor_queue.qsize() if self.executor_queue else 0
            logger.info(f"Shutting down with {events_remaining} events and {actions_remaining} actions remaining")
            
            # Cancel all tasks
            if self._tasks:
                for task in self._tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*self._tasks, return_exceptions=True)
                self._tasks = None
                
            # Close queues
            if self.collector_queue:
                await self.collector_queue.close()
            if self.executor_queue:
                await self.executor_queue.close()
                
            logger.info(
                f"Final stats - Events: collected={self.events_collected}, processed={self.events_processed}, "
                f"Actions: generated={self.actions_generated}, executed={self.actions_executed}"
            )
            
        except Exception as e:
            logger.error(f"Error stopping components: {e}")

    async def join(self):
        if self._tasks:
            await asyncio.gather(*self._tasks)

    async def _run_collector(self, collector: Collector):
        """运行单个收集器"""
        collector_name = collector.__class__.__name__
        logger.info(f"Starting collector: {collector_name}")
        
        try:
            async for event in collector.events():
                if not self.running:
                    break
                try:
                    # Store event in queue
                    start_time = time.time()
                    await self.collector_queue.put(event)
                    self.events_collected += 1
                    self.last_collector_active = time.time()
                    
                    # Log collection latency
                    latency = time.time() - start_time
                    if latency > 1.0:  # Log slow operations
                        logger.warning(f"Slow event collection in {collector_name}: {latency:.2f}s")
                        
                except Exception as e:
                    logger.error(f"Error queueing event in {collector_name}: {e}")
                    
            # 如果 events() 迭代结束，但程序还在运行，我们应该记录这个情况
            if self.running:
                logger.warning(f"Collector {collector_name} events stream ended, restarting...")
        except Exception as e:
            logger.error(f"Error in collector {collector_name}: {e}")
            if self.running:
                logger.info(f"Waiting before retrying collector {collector_name}...")
                await asyncio.sleep(5)  # 添加重试延迟

    async def _run_strategies(self):
        """Run event processing strategies"""
        logger.info("Starting strategy processor")
        last_idle_log = 0
        
        while self.running:
            try:
                # Get event from queue with timeout
                try:
                    event = await asyncio.wait_for(
                        self.collector_queue.get(),
                        timeout=self.stats_interval
                    )
                except asyncio.TimeoutError:
                    # Queue is empty - this is normal
                    now = time.time()
                    if now - last_idle_log > 60:  # Log idle status every minute
                        logger.info("Strategy processor is idle - waiting for events...")
                        last_idle_log = now
                    continue
                except Exception as e:
                    # Real error occurred
                    logger.error(f"Error reading from collector queue: {e}")
                    await asyncio.sleep(1)
                    continue

                # Process event
                self.last_strategy_active = time.time()
                start_time = time.time()
                action_count = 0
                
                for strategy in self.strategies:
                    strategy_name = strategy.__class__.__name__
                    try:
                        actions = await strategy.process_event(event)
                        for action in actions:
                            await self.executor_queue.put(action)
                            action_count += 1
                            self.actions_generated += 1
                    except Exception as e:
                        logger.error(f"Error in strategy {strategy_name}: {e}", exc_info=True)
                        
                self.events_processed += 1
                
                # Log processing metrics
                latency = time.time() - start_time
                if latency > 1.0:  # Log slow operations
                    logger.warning(f"Slow event processing: {latency:.2f}s, generated {action_count} actions")
                    
            except Exception as e:
                logger.error(f"Unexpected error in strategy processor: {e}")
                await asyncio.sleep(1)

    async def _run_executors(self):
        """Run action executors"""
        logger.info("Starting action executor")
        last_idle_log = 0
        
        while self.running:
            try:
                # Get action from queue with timeout
                try:
                    action = await asyncio.wait_for(
                        self.executor_queue.get(),
                        timeout=self.stats_interval
                    )
                except asyncio.TimeoutError:
                    # Queue is empty - this is normal
                    now = time.time()
                    if now - last_idle_log > 60:  # Log idle status every minute
                        logger.info("Action executor is idle - waiting for actions...")
                        last_idle_log = now
                    continue
                except Exception as e:
                    # Real error occurred
                    logger.error(f"Error reading from executor queue: {e}")
                    await asyncio.sleep(1)
                    continue

                # Execute action
                self.last_executor_active = time.time()
                start_time = time.time()
                
                try:
                    await asyncio.gather(
                        *(executor.execute(action) for executor in self.executors),
                        return_exceptions=True
                    )
                    
                    self.actions_executed += 1
                    
                    # Log execution metrics
                    latency = time.time() - start_time
                    if latency > 1.0:  # Log slow operations
                        logger.warning(f"Slow action execution: {latency:.2f}s")
                except Exception as e:
                    logger.error(f"Error executing action: {e}")
                    
            except Exception as e:
                logger.error(f"Unexpected error in action executor: {e}")
                await asyncio.sleep(1)

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
                events_queued = await self.collector_queue.qsize()
                actions_queued = await self.executor_queue.qsize()
                
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
                
            await asyncio.sleep(self.stats_interval)
