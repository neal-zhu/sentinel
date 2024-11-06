import asyncio
from typing import List, Union, Callable, AsyncIterable, Awaitable, Optional
from .base import (
    Collector, Strategy, Executor,
    FunctionCollector, FunctionStrategy, FunctionExecutor
)
from .events import Event, Action


class Sentinel:
    def __init__(self):
        self.collectors: List[Collector] = []
        self.strategies: List[Strategy] = []
        self.executors: List[Executor] = []
        self.running = False
        self.collector_queue = asyncio.Queue()
        self.executor_queue = asyncio.Queue()
        self._tasks: Optional[List[asyncio.Task]] = None

    def add_collector(
        self, 
        collector: Union[Collector, Callable[[], AsyncIterable[Event]]]
    ):
        if isinstance(collector, Collector):
            self.collectors.append(collector)
        else:
            self.collectors.append(FunctionCollector(collector))

    def add_strategy(
        self, 
        strategy: Union[Strategy, Callable[[Event], Awaitable[List[Action]]]]
    ):
        if isinstance(strategy, Strategy):
            self.strategies.append(strategy)
        else:
            self.strategies.append(FunctionStrategy(strategy))

    def add_executor(
        self, 
        executor: Union[Executor, Callable[[Action], Awaitable[None]]]
    ):
        if isinstance(executor, Executor):
            self.executors.append(executor)
        else:
            self.executors.append(FunctionExecutor(executor))

    async def start(self):
        self.running = True
        start_tasks = [collector.start() for collector in self.collectors]
        await asyncio.gather(*start_tasks)
        
        # Create and store all tasks
        self._tasks = [
            asyncio.create_task(self._run_collector(collector)) 
            for collector in self.collectors
        ] + [
            asyncio.create_task(self._run_strategies()),
            asyncio.create_task(self._run_executors())
        ]

    async def stop(self):
        self.running = False
        stop_tasks = [collector.stop() for collector in self.collectors]
        await asyncio.gather(*stop_tasks)
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks = None

    async def join(self):
        """Wait for all tasks to complete."""
        if self._tasks:
            await asyncio.gather(*self._tasks)

    async def _run_collector(self, collector: Collector):
        while self.running:
            async for event in collector.events():
                if not self.running:
                    break
                await self.collector_queue.put(event)

    async def _run_strategies(self):
        while self.running:
            event = await self.collector_queue.get()
            for strategy in self.strategies:
                actions = await strategy.process_event(event)
                for action in actions:
                    await self.executor_queue.put(action)
            self.collector_queue.task_done()

    async def _run_executors(self):
        while self.running:
            action = await self.executor_queue.get()
            for executor in self.executors:
                await executor.execute(action)
            self.executor_queue.task_done()
