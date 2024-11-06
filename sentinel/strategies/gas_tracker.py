from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Tuple
import heapq

from ..logger import logger

from ..core.actions import Action
from ..core.base import Strategy
from ..core.events import TransactionEvent, Event
from aioetherscan import Client


class GasTracker(Strategy):
    __component_name__ = "gas_tracker"

    def __init__(self, report_interval: int = 300, etherscan_api_key: str = None):
        super().__init__()
        # 存储不同时间窗口的数据
        self.windows = {
            '1h': 3600,
            '30min': 1800,
            '15min': 900,
            '5min': 300
        }
        # 每个时间窗口的合约 gas 使用数据
        self.gas_usage = {
            window: defaultdict(list) for window in self.windows
        }
        # 上次报告时间
        self.last_report_time = datetime.now()
        # 报告间隔（5分钟）
        self.report_interval = report_interval
        # 合约名称缓存
        self.contract_names = {}
        # Etherscan client
        if etherscan_api_key:
            self.etherscan = Client(api_key=etherscan_api_key)
        else:
            self.etherscan = None

    async def _get_contract_name(self, address: str) -> str:
        """获取合约名称，带缓存"""
        if address in self.contract_names:
            return self.contract_names[address]
        
        if not self.etherscan:
            return address[:8] + '...'
        
        try:
            # 尝试获取合约信息
            # Get contract info and check if it's a proxy
            contract_info = await self.etherscan.contract.contract_source_code(address)
            if contract_info and contract_info[0].get('Implementation'):
                # If it's a proxy, get the implementation contract info
                impl_address = contract_info[0]['Implementation']
                impl_info = await self.etherscan.contract.contract_source_code(impl_address)
                if impl_info and impl_info[0].get('ContractName'):
                    contract_info = impl_info
            name = contract_info[0]['ContractName']
            self.contract_names[address] = name
            return name
        except Exception as e:
            # 如果API调用失败，返回地址的简短形式
            logger.error(f"Failed to get contract name for {address}: {e}")
            self.contract_names[address] = address[:8] + '...'
            return self.contract_names[address]

    async def process_event(self, event: Event) -> List[Action]:
        if not isinstance(event, TransactionEvent):
            return []

        current_time = datetime.now()
        actions = []

        # 更新 gas 使用数据
        self._update_gas_usage(event, current_time)

        # 检查是否需要生成报告
        if (current_time - self.last_report_time).total_seconds() >= self.report_interval:
            report = await self._generate_report(current_time)
            actions.append(Action(
                type="gas_report",
                data=report
            ))
            self.last_report_time = current_time

        return actions

    def _update_gas_usage(self, event: TransactionEvent, current_time: datetime):
        gas_used = event.transaction.gas
        contract_address = event.transaction.to
        
        if not contract_address or not gas_used:
            return

        timestamp = current_time.timestamp()
        
        # 为每个时间窗口更新数据
        for window, seconds in self.windows.items():
            self.gas_usage[window][contract_address].append((timestamp, gas_used))
            # 清理过期数据
            self._clean_old_data(window, contract_address, timestamp - seconds)

    def _clean_old_data(self, window: str, contract: str, cutoff_time: float):
        """清理指定时间之前的数据"""
        usage_data = self.gas_usage[window][contract]
        while usage_data and usage_data[0][0] < cutoff_time:
            usage_data.pop(0)
        if not usage_data:
            del self.gas_usage[window][contract]

    def _get_top_contracts(self, window: str, current_time: float) -> List[Tuple[str, int, float]]:
        """获取指定窗口的 top 10 合约及其 gas 使用情况"""
        cutoff_time = current_time - self.windows[window]
        contract_totals = []
        
        for contract, usage_data in self.gas_usage[window].items():
            # 计算总 gas 使用量
            total_gas = sum(gas for ts, gas in usage_data if ts > cutoff_time)
            if total_gas > 0:
                # 计算变化率
                recent_gas = sum(gas for ts, gas in usage_data 
                               if ts > current_time - min(300, self.windows[window]))
                old_gas = sum(gas for ts, gas in usage_data 
                            if cutoff_time < ts <= current_time - min(300, self.windows[window]))
                
                change_rate = ((recent_gas / 300) / (old_gas / 300) - 1) * 100 if old_gas > 0 else 0
                
                contract_totals.append((contract, total_gas, change_rate))

        return heapq.nlargest(10, contract_totals, key=lambda x: x[1])

    async def _generate_report(self, current_time: datetime) -> Dict:
        """生成完整的 gas 使用报告"""
        current_ts = current_time.timestamp()
        report = {
            'timestamp': current_time.isoformat(),
            'top_contracts': {}
        }

        for window in self.windows:
            top_contracts = self._get_top_contracts(window, current_ts)
            report['top_contracts'][window] = []
            
            # 异步获取所有合约名称
            for contract, total_gas, change_rate in top_contracts:
                name = await self._get_contract_name(contract)
                report['top_contracts'][window].append({
                    'address': contract,
                    'name': name,
                    'total_gas': total_gas,
                    'change_rate': change_rate,
                    'status': self._get_status(change_rate)
                })

        return report

    def _get_status(self, change_rate: float) -> str:
        """根据变化率确定状态"""
        if change_rate > 100:
            return "急剧上升 🚀"
        elif change_rate > 50:
            return "显著上升 ⬆️"
        elif change_rate > 20:
            return "上升 📈"
        elif change_rate < -50:
            return "显著下降 ⬇️"
        elif change_rate < -20:
            return "下降 📉"
        else:
            return "稳定 ➡️"