import asyncio
from typing import List, Union, Callable, AsyncIterable, Awaitable, Optional
from contextlib import AsyncExitStack

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

    def __init__(self, queue_size: int = 1000):
        """
        Initialize Sentinel instance
        
        Args:
            queue_size: Maximum number of events/actions in queues
        """
        self.collectors: List[Collector] = []
        self.strategies: List[Strategy] = []
        self.executors: List[Executor] = []
        self.running = False
        self.collector_queue = asyncio.Queue(maxsize=queue_size)
        self.executor_queue = asyncio.Queue(maxsize=queue_size)
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

    async def start(self):
        """
        Start all components and begin processing
        
        Raises:
            Exception: If any component fails to start
        """
        self.running = True
        
        try:
            # Start all collectors
            start_tasks = [collector.start() for collector in self.collectors]
            await asyncio.gather(*start_tasks)
            
            # Create processing tasks
            self._tasks = [
                asyncio.create_task(self._run_collector(collector), name=f"collector_{i}") 
                for i, collector in enumerate(self.collectors)
            ]
            self._tasks.extend([
                asyncio.create_task(self._run_strategies(), name="strategies"),
                asyncio.create_task(self._run_executors(), name="executors")
            ])
            
            logger.info("All components started successfully")
            
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
            
            # Wait for queues to drain
            if self.collector_queue:
                await self.collector_queue.join()
            if self.executor_queue:
                await self.executor_queue.join()
            
            # Cancel all tasks
            if self._tasks:
                for task in self._tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*self._tasks, return_exceptions=True)
                self._tasks = None
                
            logger.info("All components stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping components: {e}")
            raise

    async def join(self):
        if self._tasks:
            await asyncio.gather(*self._tasks)

    async def _run_collector(self, collector: Collector):
        """运行单个收集器"""
        try:
            async for event in collector.events():
                if not self.running:
                    break
                try:
                    await self.collector_queue.put(event)
                except asyncio.QueueFull:
                        logger.warning("Collector queue is full, dropping event")
                # 如果 events() 迭代结束，但程序还在运行，我们应该记录这个情况
                if self.running:
                    logger.warning(f"Collector {collector.name} events stream ended, restarting...")
        except Exception as e:
            logger.error(f"Error in collector {collector.name}: {e}")
            if self.running:
                logger.info(f"Waiting before retrying collector {collector.name}...")
                await asyncio.sleep(5)  # 添加重试延迟

    async def _run_strategies(self):
        while self.running:
            try:
                event = await self.collector_queue.get()
                try:
                    for strategy in self.strategies:
                        actions = await strategy.process_event(event)
                        for action in actions:
                            try:
                                await self.executor_queue.put(action)
                            except asyncio.QueueFull:
                                logger.warning("Executor queue is full, dropping action")
                finally:
                    self.collector_queue.task_done()
            except Exception as e:
                logger.error(f"Error processing event: {e}", exc_info=True)

    async def _run_executors(self):
        while self.running:
            try:
                action = await self.executor_queue.get()
                try:
                    await asyncio.gather(
                        *(executor.execute(action) for executor in self.executors),
                        return_exceptions=True
                    )
                finally:
                    self.executor_queue.task_done()
            except Exception as e:
                logger.error(f"Error executing action: {e}")
