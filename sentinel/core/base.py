from abc import ABC, abstractmethod
from typing import Dict, Type, TypeVar, Optional, ClassVar, Callable, AsyncIterable, Awaitable, List
import asyncio

from .actions import Action
from .events import Event
from ..logger import logger

T = TypeVar('T', bound='Component')

class Component(ABC):
    """所有组件的基类"""
    
    _registry: ClassVar[Dict[str, Type[T]]] = {}
    _component_name: str = None
    
    def __init_subclass__(cls, **kwargs):
        """
        这个方法在子类被创建时自动调用
        只有显式设置了 __component_name__ 的类才会被注册
        """
        super().__init_subclass__(**kwargs)
        
        component_name = getattr(cls, '__component_name__', None)
        if component_name:
            # 找到最近的带有 _registry 的基类
            for base in cls.__mro__[1:]:
                if hasattr(base, '_registry'):
                    base._registry[component_name] = cls
                    cls._component_name = component_name
                    break
    
    @classmethod
    def create(cls: Type[T], name: str, **kwargs) -> T:
        """
        创建组件实例
        
        Args:
            name: 组件名称
            **kwargs: 组件初始化参数
            
        Returns:
            Component: 组件实例
            
        Raises:
            ValueError: 组件未注册
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
        """配置前缀"""
        pass
    
    @property
    def name(self) -> str:
        """组件名称"""
        return self._component_name

class Collector(Component):
    """收集器基类"""
    def __init__(self):
        self._running = False
        self._started = False
    
    @classmethod
    def config_prefix(cls) -> str:
        return "collectors"
    
    async def start(self):
        """启动收集器"""
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
        """停止收集器"""
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
        """子类可以重写此方法以实现自定义启动逻辑"""
        pass
    
    async def _stop(self):
        """子类可以重写此方法以实现自定义停止逻辑"""
        pass
    
    @property
    def is_running(self) -> bool:
        """收集器是否正在运行"""
        return self._running
    
    @abstractmethod
    async def events(self) -> AsyncIterable[Event]:
        """生成事件流"""
        pass

class Strategy(Component):
    """策略基类"""
    @classmethod
    def config_prefix(cls) -> str:
        return "strategies"
    
    @abstractmethod
    async def process_event(self, event: Event) -> List[Action]:
        """处理事件并生成动作"""
        pass

class Executor(Component):
    """执行器基类"""
    @classmethod
    def config_prefix(cls) -> str:
        return "executors"
    
    @abstractmethod
    async def execute(self, action: Action) -> None:
        """执行动作"""
        pass

# 函数包装器类
class FunctionCollector(Collector):
    """函数收集器包装器"""
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
    """函数策略包装器"""
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
    """函数执行器包装器"""
    def __init__(self, func: Callable[[Action], Awaitable[None]], name: Optional[str] = None):
        super().__init__()
        self._func = func
        self._component_name = name or func.__name__
    
    async def execute(self, action: Action) -> None:
        try:
            await self._func(action)
        except Exception as e:
            logger.error(f"Error in function executor {self.name}: {e}")
