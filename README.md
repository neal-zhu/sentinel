# Sentinel

Sentinel 是一个灵活的异步区块链事件处理框架，专注于实时监控和处理区块链事件。项目受 [Artemis](https://github.com/paradigmxyz/artemis) 启发，采用模块化的收集器(Collector)、策略(Strategy)和执行器(Executor)架构，让您能够轻松构建自定义的区块链数据处理流水线。

## 特性

- 🚀 异步设计，基于 Python asyncio
- 🔌 插件化架构，易于扩展
- 🎯 灵活的事件处理策略
- 🛠 简单的 TOML 配置

## 安装

```bash
git clone https://github.com/neal-zhu/sentinel.git
cd sentinel
pip install -r requirements.txt
```

## 快速开始

1. 复制示例配置文件：

```bash
# 复制示例配置文件
cp config.toml.example config.toml

# 根据需要修改配置
vim config.toml
```

2. 添加你需要的组件(collectors, strategies, executors), 如果需要自定义组件，请参考 [自定义组件](#高级用法)

3. 运行 Sentinel:

```bash
# 使用默认配置文件 config.toml
python -m main

# 或指定配置文件路径
python -m main -config path/to/config.toml
```

这样运行后，Sentinel 会自动加载配置文件并启动监控。您可以通过 Ctrl+C 来优雅地停止程序。

## 架构

Sentinel 采用三层架构设计：

### Collectors（收集器）
负责事件收集，支持：
- 区块链交易监控
- 智能合约事件监听
- 区块头订阅
- 自定义数据源

### Strategies（策略）
处理事件并生成操作指令：
- 交易分析
- 模式识别
- 阈值触发
- 自定义策略逻辑

### Executors（执行器）
执行策略生成的操作：
- 数据存储
- 通知推送
- API 调用
- 自定义动作

## 高级用法

### 自定义收集器

1. 创建收集器类：

```python
from sentinel.base import Collector
from sentinel.events import Event

class CustomCollector(Collector):
    async def events(self):
        while True:
            # 自定义事件收集逻辑
            yield Event(name="custom", data={"key": "value"})
            await asyncio.sleep(1)
```

2. 在 `sentinel/collectors/__init__.py` 中注册：

```python
from .custom import CustomCollector

__all__ = [
    "CustomCollector",
    # ... 其他收集器
]
```

### 自定义策略

1. 创建策略类：

```python
from sentinel.base import Strategy
from sentinel.events import Event, Action

class PriceAlertStrategy(Strategy):
    async def process_event(self, event: Event) -> List[Action]:
        if event.name == "price_update":
            if event.data["price"] > 1000:
                return [Action(name="alert", data={"message": "Price threshold exceeded!"})]
        return []
```

2. 在 `sentinel/strategies/__init__.py` 中注册：

```python
from .price_alert import PriceAlertStrategy

__all__ = [
    "PriceAlertStrategy",
    # ... 其他策略
]
```

### 自定义执行器

1. 创建执行器类：

```python
from sentinel.base import Executor
from sentinel.events import Action

class CustomExecutor(Executor):
    async def execute(self, action: Action):
        # 自定义执行逻辑
        print(f"Executing action: {action.name}")
```

2. 在 `sentinel/executors/__init__.py` 中注册：

```python
from .custom import CustomExecutor

__all__ = [
    "CustomExecutor",
    # ... 其他执行器
]
```

注册完成后，您就可以在配置文件中使用这些自定义组件：

```toml
[collectors]
enabled = ["custom"]

[strategies]
enabled = ["price_alert"]

[executors]
enabled = ["custom"]
```

## 配置参考

完整的配置选项：

```toml
# General Settings
name = "sentinel"
log_level = "INFO"

# Collectors Configuration
[collectors]
enabled = ["web3_transaction"]

[collectors.web3_transaction]
rpc_url = "https://eth.llamarpc.com"

# Strategies Configuration
[strategies]
enabled = ["dummy"]

[executors]
enabled = ["logger"]

```

## 开发计划

- [ ] 支持更多区块链网络
- [ ] 增加更多预置策略
- [ ] 优化性能和资源使用

## 贡献

欢迎提交 Pull Requests！对于重大更改，请先开 issue 讨论您想要更改的内容。

## 致谢

- 感谢 [Artemis](https://github.com/paradigmxyz/artemis) 项目的启发
- 感谢所有贡献者的支持

## 许可证

[MIT](LICENSE)

## 联系方式

如有问题或建议，请提交 issue。