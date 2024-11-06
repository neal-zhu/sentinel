from abc import ABC, abstractmethod
from typing import Dict, Type, TypeVar, Optional, ClassVar, Callable, AsyncIterable, Awaitable, List
from ..core.events import Event, Action

from sentinel.core.events import Event

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
        
        # 获取组件名称
        component_name = getattr(cls, '__component_name__', None)
        
        if component_name:
            # 找到最近的带有 _registry 的基类
            for base in cls.__mro__[1:]:  # 跳过自身
                if hasattr(base, '_registry'):
                    base._registry[component_name] = cls
                    cls._component_name = component_name
                    break
    
    @classmethod
    def create(cls: Type[T], name: str, **kwargs) -> T:
        if name not in cls._registry:
            raise ValueError(f"No {cls.__name__} registered with name: {name}")
            
        # 获取组件类
        component_class = cls._registry[name]
        
        return component_class(**kwargs)
    
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
        self._started = True
        self._running = True
        await self._start()
    
    async def stop(self):
        """停止收集器"""
        if not self._started:
            return
        self._running = False
        await self._stop()
        self._started = False
    
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
        return await self._func(event)

class FunctionExecutor(Executor):
    """函数执行器包装器"""
    def __init__(self, func: Callable[[Action], Awaitable[None]], name: Optional[str] = None):
        super().__init__()
        self._func = func
        self._component_name = name or func.__name__
    
    async def execute(self, action: Action) -> None:
        await self._func(action)

# 装饰器
def function_collector(name: Optional[str] = None):
    """装饰器：将异步生成器函数转换为收集器"""
    def wrapper(func: Callable[[], AsyncIterable[Event]]) -> FunctionCollector:
        return FunctionCollector(func, name)
    return wrapper

def function_strategy(name: Optional[str] = None):
    """装饰器：将异步函数转换为策略"""
    def wrapper(func: Callable[[Event], Awaitable[List[Action]]]) -> FunctionStrategy:
        return FunctionStrategy(func, name)
    return wrapper

def function_executor(name: Optional[str] = None):
    """装饰器：将异步函数转换为执行器"""
    def wrapper(func: Callable[[Action], Awaitable[None]]) -> FunctionExecutor:
        return FunctionExecutor(func, name)
    return wrapper
