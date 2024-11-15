import asyncio
import pytest
from datetime import datetime
from hexbytes import HexBytes
from web3.types import BlockData, TxData

from sentinel.core.events import Event, TransactionEvent
from sentinel.core.actions import Action
from sentinel.config import Config
from sentinel.core.sentinel import Sentinel

# 模拟区块数据
MOCK_BLOCK = {
    'number': 1000,
    'timestamp': int(datetime.now().timestamp()),
    'hash': HexBytes('0x00'),
    'transactions': [{
        'hash': HexBytes('0x1234'),
        'from': '0xsender',
        'to': '0xreceiver',
        'value': 1000000,
        'gas': 21000,
        'gasPrice': 20000000000,
        'nonce': 0,
        'blockHash': HexBytes('0x00'),
        'blockNumber': 1000,
        'transactionIndex': 0,
    }]
}

# 模拟收集器
async def mock_collector():
    for i in range(3):
        yield TransactionEvent(
            transaction=MOCK_BLOCK['transactions'][0],
            block=MOCK_BLOCK,
            timestamp=datetime.fromtimestamp(MOCK_BLOCK['timestamp'])
        )
        await asyncio.sleep(0.1)

# 模拟策略
async def mock_strategy(event: Event) -> list[Action]:
    return [Action(
        type="test_action",
        data={"event_type": event.type, "timestamp": str(datetime.now())}
    )]

# 记录执行的动作
executed_actions = []

# 模拟执行器
async def mock_executor(action: Action):
    executed_actions.append(action)

@pytest.mark.asyncio
async def test_basic_flow():
    """测试基本的事件流程"""
    # 创建 Sentinel 实例
    sentinel = Sentinel()
    
    # 添加组件
    sentinel.add_collector(mock_collector)
    sentinel.add_strategy(mock_strategy)
    sentinel.add_executor(mock_executor)
    
    # 启动处理
    await sentinel.start()
    
    # 等待一段时间让事件处理完成
    await asyncio.sleep(1)
    
    # 停止处理
    await sentinel.stop()
    
    # 验证结果
    assert len(executed_actions) == 3
    for action in executed_actions:
        assert action.type == "test_action"
        assert "event_type" in action.data
        assert action.data["event_type"] == "transaction"

@pytest.mark.asyncio
async def test_config_loading():
    """测试配置加载"""
    config = Config("config.toml.example")
    
    assert "web3_transaction" in config.collectors
    assert "wxpusher" in config.get("executors", {}).get("enabled", [])
    
    collector_config = config.get_collector_config("web3_transaction")
    assert "rpc_url" in collector_config

def test_event_creation():
    """测试事件创建"""
    event = TransactionEvent(
        transaction=MOCK_BLOCK['transactions'][0],
        block=MOCK_BLOCK,
        timestamp=datetime.fromtimestamp(MOCK_BLOCK['timestamp'])
    )
    
    assert event.type == "transaction"
    assert event.transaction['hash'] == HexBytes('0x1234')
    assert event.block['number'] == 1000

def test_action_creation():
    """测试动作创建"""
    action = Action(
        type="test",
        data={"key": "value"}
    )
    
    assert action.type == "test"
    assert action.data["key"] == "value" 