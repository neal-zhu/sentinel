"""
Basic test suite for Sentinel

Tests:
- Basic event flow
- Configuration loading
- Event and action creation
- Component integration
"""

import asyncio
import pytest
from datetime import datetime
from hexbytes import HexBytes
from web3.types import BlockData, TxData

from sentinel.core.events import Event, TransactionEvent
from sentinel.core.actions import Action
from sentinel.config import Config
from sentinel.core.sentinel import Sentinel

# Mock block data
MOCK_BLOCK: dict = {
    'number': 1000,
    'timestamp': int(datetime.now().timestamp()),
    'hash': HexBytes('0xabcd1234'),
    'transactions': [{
        'hash': HexBytes('0x1234abcd'),
        'from': '0xsender',
        'to': '0xreceiver',
        'value': 1000000,
        'gas': 21000,
        'gasPrice': 20000000000,
        'nonce': 0,
        'blockHash': HexBytes('0xabcd1234'),
        'blockNumber': 1000,
        'transactionIndex': 0,
    }]
}

# Mock collector
async def mock_collector():
    """Generate mock transaction events"""
    for i in range(3):
        yield TransactionEvent(
            transaction=MOCK_BLOCK['transactions'][0],
            block=MOCK_BLOCK,
            timestamp=datetime.fromtimestamp(MOCK_BLOCK['timestamp'])
        )
        await asyncio.sleep(0.01)  # 减少等待时间

# Mock strategy
async def mock_strategy(event: Event) -> list[Action]:
    """Generate test actions from events"""
    return [Action(
        type="test_action",
        data={"event_type": event.type, "timestamp": str(datetime.now())}
    )]

# Track executed actions
executed_actions = []

# Mock executor
async def mock_executor(action: Action):
    """Record executed actions"""
    executed_actions.append(action)

@pytest.fixture(autouse=True)
def clear_executed_actions():
    """Clear executed actions before each test"""
    executed_actions.clear()
    yield

@pytest.mark.asyncio
async def test_basic_flow():
    """Test basic event processing flow"""
    # 清空执行操作列表
    executed_actions.clear()
    
    # 创建一个简单的自定义异步生成器函数
    async def simple_collector():
        # 只生成3个事件，不使用sleep
        for i in range(3):
            yield TransactionEvent(
                transaction=MOCK_BLOCK['transactions'][0],
                block=MOCK_BLOCK,
                timestamp=datetime.fromtimestamp(MOCK_BLOCK['timestamp'])
            )
    
    sentinel = Sentinel()
    sentinel.add_collector(simple_collector)
    sentinel.add_strategy(mock_strategy)
    sentinel.add_executor(mock_executor)
    
    # 使用短的timeout来限制start和stop的执行时间
    try:
        # 启动并运行一小段时间
        await asyncio.wait_for(sentinel.start(), timeout=2.0)
        await asyncio.sleep(2.0)  # 等待2秒处理事件
        await asyncio.wait_for(sentinel.stop(grace_period=2.0), timeout=3.0)
        
        # 验证结果
        assert len(executed_actions) == 3
        for action in executed_actions:
            assert action.type == "test_action"
            assert "event_type" in action.data
            assert action.data["event_type"] == "transaction"
    except asyncio.TimeoutError:
        # 如果等待超时，强制关闭并报告
        await sentinel.stop(grace_period=0.1)
        assert False, "Test timed out, execution took too long"

@pytest.mark.asyncio
async def test_config_loading():
    """Test configuration loading"""
    # Create a temporary config file for testing
    import tempfile
    import tomli_w
    
    config_data = {
        "collectors": {
            "enabled": ["web3_transaction"],
            "web3_transaction": {
                "rpc_url": "https://eth.llamarpc.com"
            }
        },
        "executors": {
            "enabled": ["wxpusher"]
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.toml', delete=False) as f:
        tomli_w.dump(config_data, f)
        config_path = f.name
    
    config = Config(config_path)
    
    assert "web3_transaction" in config.collectors
    assert "wxpusher" in config.executors
    
    collector_config = config.get_collector_config("web3_transaction")
    assert "rpc_url" in collector_config

def test_event_creation():
    """Test event object creation"""
    event = TransactionEvent(
        transaction=MOCK_BLOCK['transactions'][0],
        block=MOCK_BLOCK,
        timestamp=datetime.fromtimestamp(MOCK_BLOCK['timestamp'])
    )
    
    assert event.type == "transaction"
    assert event.transaction['hash'] == MOCK_BLOCK['transactions'][0]['hash']
    assert event.block['number'] == MOCK_BLOCK['number']

def test_action_creation():
    """Test action object creation"""
    action = Action(
        type="test",
        data={"key": "value"}
    )
    
    assert action.type == "test"
    assert action.data["key"] == "value" 