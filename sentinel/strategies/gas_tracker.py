"""
Gas usage tracking strategy

Monitors and analyzes gas usage patterns across different time windows:
- Tracks gas consumption by contract
- Generates periodic reports
- Identifies usage trends
- Provides contract name resolution via Etherscan
"""

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
    """
    Strategy for tracking gas usage patterns across different time windows
    
    Features:
    - Multiple time window analysis (e.g., 5min, 15min, 30min, 1h)
    - Contract name resolution with caching
    - Trend detection and status reporting
    - Periodic report generation
    """
    
    __component_name__ = "gas_tracker"

    def __init__(self, windows: Dict[str, int] = None):
        """
        Initialize gas tracker
        
        Args:
            windows: Time window configuration, e.g., {"1h": 3600, "30min": 1800}
                    Defaults to {"1h": 3600, "24h": 86400}
        """
        super().__init__()
        self.windows = windows or {"1h": 3600, "24h": 86400}
        self.gas_usage = defaultdict(lambda: defaultdict(list))  # window -> contract -> [(timestamp, gas)]
        self.last_report_time = datetime.now()
        self.report_interval = 300  # Generate report every 5 minutes
        self.contract_names = {}  # Contract name cache
        self.etherscan = None  # Etherscan client

    async def _get_contract_name(self, address: str) -> str:
        """
        Get contract name with caching
        
        Args:
            address: Contract address
            
        Returns:
            str: Contract name or shortened address if not found
        """
        if address in self.contract_names:
            return self.contract_names[address]
        
        if not self.etherscan:
            return address[:8] + '...'
        
        try:
            # Try to get contract info
            contract_info = await self.etherscan.contract.contract_source_code(address)
            if contract_info and contract_info[0].get('Implementation'):
                # If proxy contract, get implementation contract info
                impl_address = contract_info[0]['Implementation']
                impl_info = await self.etherscan.contract.contract_source_code(impl_address)
                if impl_info and impl_info[0].get('ContractName'):
                    contract_info = impl_info
            name = contract_info[0]['ContractName']
            self.contract_names[address] = name
            return name
        except Exception as e:
            logger.error(f"Failed to get contract name for {address}: {e}")
            self.contract_names[address] = address[:8] + '...'
            return self.contract_names[address]

    async def process_event(self, event: Event) -> List[Action]:
        """
        Process transaction event and generate gas report if needed
        
        Args:
            event: Event to process
            
        Returns:
            List[Action]: List of actions to execute
        """
        if not isinstance(event, TransactionEvent):
            return []

        current_time = datetime.now()
        actions = []

        # Update gas usage data
        self._update_gas_usage(event.tx_data, current_time)

        # Check if report should be generated
        if (current_time - self.last_report_time).total_seconds() >= self.report_interval:
            report = await self._generate_report(current_time)
            actions.append(Action(
                type="gas_report",
                data=report
            ))
            self.last_report_time = current_time

        return actions

    def _update_gas_usage(self, tx_data: Dict, current_time: datetime):
        """
        Update gas usage data for all time windows
        
        Args:
            tx_data: Transaction data
            current_time: Current timestamp
        """
        gas_used = tx_data.get('gas', 0)
        contract_address = tx_data.get('to')
        
        if not contract_address or not gas_used:
            return

        timestamp = current_time.timestamp()
        
        # Update data for each time window
        for window, seconds in self.windows.items():
            self.gas_usage[window][contract_address].append((timestamp, gas_used))
            # Clean old data
            self._clean_old_data(window, contract_address, timestamp - seconds)

    def _clean_old_data(self, window: str, contract: str, cutoff_time: float):
        """
        Clean data older than cutoff time
        
        Args:
            window: Time window name
            contract: Contract address
            cutoff_time: Cutoff timestamp
        """
        usage_data = self.gas_usage[window][contract]
        while usage_data and usage_data[0][0] < cutoff_time:
            usage_data.pop(0)
        if not usage_data:
            del self.gas_usage[window][contract]

    def _get_top_contracts(self, window: str, current_time: float) -> List[Tuple[str, int, float]]:
        """
        Get top 10 contracts by gas usage for specified window
        
        Args:
            window: Time window name
            current_time: Current timestamp
            
        Returns:
            List[Tuple[str, int, float]]: List of (contract_address, total_gas, change_rate)
        """
        cutoff_time = current_time - self.windows[window]
        contract_totals = []
        
        for contract, usage_data in self.gas_usage[window].items():
            # Calculate total gas usage
            total_gas = sum(gas for ts, gas in usage_data if ts > cutoff_time)
            if total_gas > 0:
                # Calculate change rate
                recent_gas = sum(gas for ts, gas in usage_data 
                               if ts > current_time - min(300, self.windows[window]))
                old_gas = sum(gas for ts, gas in usage_data 
                            if cutoff_time < ts <= current_time - min(300, self.windows[window]))
                
                change_rate = ((recent_gas / 300) / (old_gas / 300) - 1) * 100 if old_gas > 0 else 0
                
                contract_totals.append((contract, total_gas, change_rate))

        return heapq.nlargest(10, contract_totals, key=lambda x: x[1])

    async def _generate_report(self, current_time: datetime) -> Dict:
        """
        Generate comprehensive gas usage report
        
        Args:
            current_time: Current timestamp
            
        Returns:
            Dict: Report data containing top contracts and their usage statistics
        """
        current_ts = current_time.timestamp()
        report = {
            'timestamp': current_time.isoformat(),
            'top_contracts': {}
        }

        for window in self.windows:
            top_contracts = self._get_top_contracts(window, current_ts)
            report['top_contracts'][window] = []
            
            # Get contract names asynchronously
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
        """
        Get status indicator based on change rate
        
        Args:
            change_rate: Gas usage change rate in percentage
            
        Returns:
            str: Status indicator with emoji
        """
        if change_rate > 100:
            return "Surging 🚀"
        elif change_rate > 50:
            return "Rising Fast ⬆️"
        elif change_rate > 20:
            return "Rising 📈"
        elif change_rate < -50:
            return "Dropping Fast ⬇️"
        elif change_rate < -20:
            return "Dropping 📉"
        else:
            return "Stable ➡️"
