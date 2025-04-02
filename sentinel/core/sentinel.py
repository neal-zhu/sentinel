import asyncio
import os
import time
from typing import Any, AsyncIterable, Awaitable, Callable, List, Optional, Union

from aiodiskqueue import Queue

from ..logger import logger
from .actions import Action
from .base import (
    Collector,
    Executor,
    FunctionCollector,
    FunctionExecutor,
    FunctionStrategy,
    Strategy,
)
from .events import Event
from .stats import StatsManager


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
        self.running: bool = False

        # Ensure queue directory exists
        os.makedirs(queue_dir, exist_ok=True)

        # Queue paths
        self.collector_queue_path: str = os.path.join(
            queue_dir, f"{group_name}_events.db"
        )
        self.executor_queue_path: str = os.path.join(
            queue_dir, f"{group_name}_actions.db"
        )

        # Queues will be initialized in start()
        self.collector_queue: Queue[Event] = None  # type: ignore
        self.executor_queue: Queue[Action] = None  # type: ignore

        self._tasks: Optional[List[asyncio.Task[Any]]] = None

        # Initialize stats manager
        self.stats = StatsManager(
            stats_interval=stats_interval,
            get_collector_queue_size=lambda: self.collector_queue.qsize()
            if self.collector_queue
            else 0,
            get_executor_queue_size=lambda: self.executor_queue.qsize()
            if self.executor_queue
            else 0,
        )

    def add_collector(
        self, collector: Union[Collector, Callable[[], AsyncIterable[Event]]]
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
        self, strategy: Union[Strategy, Callable[[Event], Awaitable[List[Action]]]]
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
        self, executor: Union[Executor, Callable[[Action], Awaitable[None]]]
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
                    self._run_collector(collector), name=f"collector_{i}"
                )
                self._tasks.append(task)

            # Add core tasks
            core_tasks = [
                asyncio.create_task(self._run_strategies(), name="strategies"),
                asyncio.create_task(self._run_executors(), name="executors"),
            ]
            self._tasks.extend(core_tasks)

            # Start stats manager
            stats_task = await self.stats.start()
            self._tasks.append(stats_task)

            # Log start rather than waiting for tasks to complete
            logger.info(
                f"Started {len(self.collectors)} collectors, {len(self.strategies)} strategies, {len(self.executors)} executors"
            )

        except Exception as e:
            logger.error(f"Error starting components: {e}")
            await self.stop()
            raise

    async def stop(self, grace_period: float = 5.0, force_timeout: float = 15.0):
        """
        Stop all components gracefully with a forced timeout

        Ensures all queued events are processed before shutting down,
        but guarantees shutdown within force_timeout seconds

        Args:
            grace_period: Time in seconds to wait for in-progress tasks to complete
            force_timeout: Maximum time to wait before forcing shutdown
        """
        # Prevent multiple stop calls
        if not self.running:
            logger.info("Stop called on already stopped Sentinel")
            return

        self.running = False
        logger.info("Stopping Sentinel...")

        try:
            # Set up a shield around the entire shutdown process with a hard timeout
            try:
                # Create a task for the graceful shutdown
                shutdown_task = asyncio.create_task(
                    self._graceful_shutdown(grace_period)
                )

                # Wait for graceful shutdown with a hard timeout
                await asyncio.wait_for(shutdown_task, timeout=force_timeout)
                logger.info("Graceful shutdown completed")

            except asyncio.TimeoutError:
                logger.warning(
                    f"Graceful shutdown timed out after {force_timeout}s, forcing immediate shutdown"
                )
            except Exception as e:
                logger.error(f"Error during graceful shutdown: {e}")

            # Final cleanup - ensure all tasks are cancelled
            if self._tasks:
                logger.info("Forcefully cancelling all remaining tasks")
                for task in self._tasks:
                    if not task.done():
                        task.cancel()

                # Wait very briefly for tasks to terminate
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*self._tasks, return_exceptions=True),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    logger.warning("Some tasks did not terminate within timeout period")

                self._tasks = None

            logger.info("Sentinel shutdown complete")

        except Exception as e:
            logger.error(f"Error stopping components: {e}")

    async def join(self):
        """
        Wait for all tasks to complete

        This method is typically used in production to keep the main task running
        until an external signal (like SIGINT) is received. It should not be used
        in tests where you want to control execution flow explicitly.

        In tests, use `start()` followed by a controlled sleep and then `stop()`.
        """
        if not self._tasks:
            logger.warning("Sentinel.join() called before start() or after stop()")
            return

        # Focus on core tasks which should keep running
        core_tasks = [
            task
            for task in self._tasks
            if task.get_name() in ("strategies", "executors")
        ]
        if not core_tasks:
            logger.warning("No core tasks found to join")
            return

        try:
            # Wait for any of the core tasks to complete or be cancelled
            # In normal operation, these should run indefinitely until stop() is called
            done, pending = await asyncio.wait(
                core_tasks, return_when=asyncio.FIRST_COMPLETED
            )

            # Check if any task completed with an error
            for task in done:
                if not task.cancelled() and task.exception():
                    logger.error(
                        f"Task {task.get_name()} failed with exception: {task.exception()}"
                    )

        except asyncio.CancelledError:
            logger.info("Join operation cancelled")
        except Exception as e:
            logger.error(f"Error during join: {e}")

    async def _graceful_shutdown(self, grace_period: float):
        """Internal helper for graceful shutdown sequence"""
        try:
            # Stop collectors first to prevent new events
            if self.collectors:
                logger.info(f"Stopping {len(self.collectors)} collectors...")
                stop_tasks = [collector.stop() for collector in self.collectors]
                await asyncio.gather(*stop_tasks, return_exceptions=True)

            # Give in-progress tasks time to complete
            logger.info(f"Waiting up to {grace_period}s for in-progress tasks...")

            # Wait for grace period or until all processing is idle
            shutdown_start = time.time()
            while time.time() - shutdown_start < grace_period:
                # Check if both processors are idle (no active tasks)
                strategy_idle = time.time() - self.stats.last_strategy_active > 1.0
                executor_idle = time.time() - self.stats.last_executor_active > 1.0

                if strategy_idle and executor_idle:
                    logger.info("All in-progress tasks completed")
                    break

                await asyncio.sleep(0.2)  # Check status more frequently

            # Log final queue sizes
            events_remaining = (
                self.collector_queue.qsize() if self.collector_queue else 0
            )
            actions_remaining = (
                self.executor_queue.qsize() if self.executor_queue else 0
            )
            logger.info(
                f"Shutdown progress: {events_remaining} events and {actions_remaining} actions remaining"
            )

            # Stop stats manager
            await self.stats.stop()

        except Exception as e:
            logger.error(f"Error in graceful shutdown: {e}")

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
                    self.stats.on_event_collected()

                    # Log collection latency
                    latency = time.time() - start_time
                    if latency > 1.0:  # Log slow operations
                        logger.warning(
                            f"Slow event collection in {collector_name}: {latency:.2f}s"
                        )

                except Exception as e:
                    logger.error(f"Error queueing event in {collector_name}: {e}")

            # 如果 events() 迭代结束，但程序还在运行，我们应该记录这个情况
            if self.running:
                logger.warning(
                    f"Collector {collector_name} events stream ended, restarting..."
                )
        except Exception as e:
            logger.error(f"Error in collector {collector_name}: {e}")
            if self.running:
                logger.info(f"Waiting before retrying collector {collector_name}...")
                await asyncio.sleep(5)  # 添加重试延迟

    async def _run_strategies(self):
        """Run event processing strategies"""
        logger.info("Starting strategy processor")
        last_idle_log = 0
        # Using a short timeout so we can check running flag frequently
        SHORT_TIMEOUT = 2.0  # 2 seconds timeout for queue operations

        try:
            while self.running:
                try:
                    # Get event from queue with short timeout
                    try:
                        # Use shorter timeout to check running flag more frequently
                        with_timeout = asyncio.wait_for(
                            asyncio.shield(self.collector_queue.get()),
                            timeout=SHORT_TIMEOUT,
                        )

                        # Allow for cancellation check before potentially blocking operation
                        event = await with_timeout

                    except asyncio.TimeoutError:
                        # Queue is empty - this is normal
                        now = time.time()
                        if now - last_idle_log > 60:  # Log idle status every minute
                            logger.info(
                                "Strategy processor is idle - waiting for events..."
                            )
                            last_idle_log = now
                        continue
                    except asyncio.CancelledError:
                        # Task was cancelled, exit gracefully
                        logger.info(
                            "Strategy processor task cancelled, shutting down..."
                        )
                        return
                    except Exception as e:
                        # Real error occurred
                        logger.error(f"Error reading from collector queue: {e}")
                        await asyncio.sleep(1)
                        continue

                    # Process event
                    start_time = time.time()
                    action_count = 0

                    for strategy in self.strategies:
                        if not self.running:
                            break

                        strategy_name = strategy.__class__.__name__
                        try:
                            actions = await strategy.process_event(event)
                            for action in actions:
                                if not self.running:
                                    break
                                await self.executor_queue.put(action)
                                action_count += 1
                                self.stats.on_action_generated()
                        except Exception as e:
                            logger.error(
                                f"Error in strategy {strategy_name}: {e}", exc_info=True
                            )

                    self.stats.on_event_processed()

                    # Log processing metrics
                    latency = time.time() - start_time
                    if latency > 1.0:  # Log slow operations
                        logger.warning(
                            f"Slow event processing: {latency:.2f}s, generated {action_count} actions"
                        )

                except Exception as e:
                    logger.error(f"Unexpected error in strategy processor: {e}")
                    await asyncio.sleep(1)

                # Allow task cancellation to be processed between events
                await asyncio.sleep(0)

        except asyncio.CancelledError:
            logger.info("Strategy processor task cancelled, shutting down...")
        except Exception as e:
            logger.error(f"Fatal error in strategy processor: {e}", exc_info=True)
        finally:
            logger.info("Strategy processor stopped")

    async def _run_executors(self):
        """Run action executors"""
        logger.info("Starting action executor")
        last_idle_log = 0
        # Using a short timeout so we can check running flag frequently
        SHORT_TIMEOUT = 2.0  # 2 seconds timeout for queue operations

        try:
            while self.running:
                try:
                    # Get action from queue with short timeout
                    try:
                        # Use shorter timeout to check running flag more frequently
                        with_timeout = asyncio.wait_for(
                            asyncio.shield(self.executor_queue.get()),
                            timeout=SHORT_TIMEOUT,
                        )

                        # Allow for cancellation check before potentially blocking operation
                        action = await with_timeout

                    except asyncio.TimeoutError:
                        # Queue is empty - this is normal
                        now = time.time()
                        if now - last_idle_log > 60:  # Log idle status every minute
                            logger.info(
                                "Action executor is idle - waiting for actions..."
                            )
                            last_idle_log = now
                        continue
                    except asyncio.CancelledError:
                        # Task was cancelled, exit gracefully
                        logger.info("Action executor task cancelled, shutting down...")
                        return
                    except Exception as e:
                        # Real error occurred
                        logger.error(f"Error reading from executor queue: {e}")
                        await asyncio.sleep(1)
                        continue

                    # Execute action
                    start_time = time.time()

                    try:
                        if self.running:
                            await asyncio.gather(
                                *(
                                    executor.execute(action)
                                    for executor in self.executors
                                ),
                                return_exceptions=True,
                            )

                            self.stats.on_action_executed()

                            # Log execution metrics
                            latency = time.time() - start_time
                            if latency > 1.0:  # Log slow operations
                                logger.warning(f"Slow action execution: {latency:.2f}s")
                    except Exception as e:
                        logger.error(f"Error executing action: {e}")

                except Exception as e:
                    logger.error(f"Unexpected error in action executor: {e}")
                    await asyncio.sleep(1)

                # Allow task cancellation to be processed between actions
                await asyncio.sleep(0)

        except asyncio.CancelledError:
            logger.info("Action executor task cancelled, shutting down...")
        except Exception as e:
            logger.error(f"Fatal error in action executor: {e}", exc_info=True)
        finally:
            logger.info("Action executor stopped")
