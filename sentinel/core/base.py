from abc import ABC, abstractmethod
from typing import Dict, Type, TypeVar, Optional, ClassVar, Callable, AsyncIterable, Awaitable, List
import asyncio

from .actions import Action
from .events import Event
from ..logger import logger

T = TypeVar('T', bound='Component')

class Component(ABC):
    """All components base class"""
    
    _registry: ClassVar[Dict[str, Type[T]]] = {}
    _component_name: str = None
    
    def __init_subclass__(cls, **kwargs):
        """
        This method is called automatically when a subclass is created
        Only classes with explicitly set __component_name__ will be registered
        """
        super().__init_subclass__(**kwargs)
        
        component_name = getattr(cls, '__component_name__', None)
        if component_name:
            # Find the nearest base class with _registry
            for base in cls.__mro__[1:]:
                if hasattr(base, '_registry'):
                    base._registry[component_name] = cls
                    cls._component_name = component_name
                    break
    
    @classmethod
    def create(cls: Type[T], name: str, **kwargs) -> T:
        """
        Create component instance
        
        Args:
            name: Component name
            **kwargs: Component initialization parameters
            
        Returns:
            Component: Component instance
            
        Raises:
            ValueError: Component not registered
        """
        if name not in cls._registry:
            raise ValueError(f"No {cls.__name__} registered with name: {name}")
        
        try:
            component_class = cls._registry[name]
            return component_class(**kwargs)
        except Exception as e:
            logger.error(f"Error creating component {name}: {e}")
            raise
    
    @classmethod
    @abstractmethod
    def config_prefix(cls) -> str:
        """Configuration prefix"""
        pass
    
    @property
    def name(self) -> str:
        """Component name"""
        return self._component_name

class Collector(Component):
    """Collector base class"""
    def __init__(self):
        self._running = False
        self._started = False
    
    @classmethod
    def config_prefix(cls) -> str:
        return "collectors"
    
    async def start(self):
        """Start collector"""
        if self._started:
            return
        try:
            self._started = True
            self._running = True
            await self._start()
            logger.info(f"Collector {self.name} started")
        except Exception as e:
            self._started = False
            self._running = False
            logger.error(f"Error starting collector {self.name}: {e}")
            raise
    
    async def stop(self):
        """Stop collector"""
        if not self._started:
            return
        try:
            self._running = False
            await self._stop()
            self._started = False
            logger.info(f"Collector {self.name} stopped")
        except Exception as e:
            logger.error(f"Error stopping collector {self.name}: {e}")
            raise
    
    async def _start(self):
        """Subclasses can override this method to implement custom startup logic"""
        pass
    
    async def _stop(self):
        """Subclasses can override this method to implement custom shutdown logic"""
        pass
    
    @property
    def is_running(self) -> bool:
        """Whether the collector is running"""
        return self._running
    
    @abstractmethod
    async def events(self) -> AsyncIterable[Event]:
        """Generate event stream"""
        pass
        
    def __aiter__(self):
        """Make Collector an async iterator
        
        Returns self as the iterator since events() already provides the async iteration interface
        """
        return self

class Strategy(Component):
    """Strategy base class"""
    @classmethod
    def config_prefix(cls) -> str:
        return "strategies"
    
    @abstractmethod
    async def process_event(self, event: Event) -> List[Action]:
        """Process event and generate actions"""
        pass

class Executor(Component):
    """Executor base class"""
    @classmethod
    def config_prefix(cls) -> str:
        return "executors"
    
    @abstractmethod
    async def execute(self, action: Action) -> None:
        """Execute action"""
        pass

# Function collector wrapper
class FunctionCollector(Collector):
    """Function collector wrapper"""
    def __init__(self, func: Callable[[], AsyncIterable[Event]], name: Optional[str] = None):
        super().__init__()
        self._func = func
        self._component_name = name or func.__name__
    
    async def events(self) -> AsyncIterable[Event]:
        if not self._started:
            await self.start()
        
        try:
            async for event in self._func():
                if not self._running:
                    break
                yield event
        except Exception as e:
            logger.error(f"Error in function collector {self.name}: {e}")
            raise
        finally:
            if self._running:
                await self.stop()

class FunctionStrategy(Strategy):
    """Function strategy wrapper"""
    def __init__(self, func: Callable[[Event], Awaitable[List[Action]]], name: Optional[str] = None):
        super().__init__()
        self._func = func
        self._component_name = name or func.__name__
    
    async def process_event(self, event: Event) -> List[Action]:
        try:
            return await self._func(event)
        except Exception as e:
            logger.error(f"Error in function strategy {self.name}: {e}")
            return []

class FunctionExecutor(Executor):
    """Function executor wrapper"""
    def __init__(self, func: Callable[[Action], Awaitable[None]], name: Optional[str] = None):
        super().__init__()
        self._func = func
        self._component_name = name or func.__name__
    
    async def execute(self, action: Action) -> None:
        try:
            await self._func(action)
        except Exception as e:
            logger.error(f"Error in function executor {self.name}: {e}")
