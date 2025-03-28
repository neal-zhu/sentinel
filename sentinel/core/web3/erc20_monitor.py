from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from web3 import Web3
from web3.contract import Contract
from eth_typing import Address

from .multi_provider import MultiNodeProvider
from .base import (
    ERC20_ABI,
    TRANSFER_EVENT_TOPIC,
    format_token_amount,
    parse_transfer_event,
    is_known_protocol
)
from sentinel.logger import logger

class ERC20Monitor:
    """Monitors and analyzes ERC20 token transfers."""
    
    def __init__(
        self,
        provider: MultiNodeProvider,
        token_address: str,
        min_amount: float = 1000.0,  # Minimum amount to track
        time_window: int = 3600,  # Time window in seconds for analysis
        known_addresses: Optional[List[str]] = None
    ):
        """
        Initialize the ERC20 monitor.
        
        Args:
            provider: MultiNodeProvider instance for Web3 interactions
            token_address: Address of the token to monitor
            min_amount: Minimum token amount to track
            time_window: Time window in seconds for analyzing patterns
            known_addresses: List of known addresses to track
        """
        self.provider = provider
        self.w3 = Web3(provider)
        self.token_address = Web3.to_checksum_address(token_address)
        self.min_amount = min_amount
        self.time_window = time_window
        self.known_addresses = set(addr.lower() for addr in (known_addresses or []))
        
        # Initialize token contract
        self.contract: Contract = self.w3.eth.contract(
            address=self.token_address,
            abi=ERC20_ABI
        )
        
        # Initialize properties that will be set during initialize()
        self.decimals = None
        self.symbol = None
        self.name = None
        
        # Initialize tracking structures
        self.transfers: List[Dict[str, Any]] = []
        self.address_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "total_volume": 0,
            "transfer_count": 0,
            "last_transfer": None,
            "protocol_interactions": 0
        })
        
    async def initialize(self):
        """Initialize token information and historical data."""
        try:
            # Get token information
            self.decimals = await self.contract.functions.decimals().call()
            self.symbol = await self.contract.functions.symbol().call()
            self.name = await self.contract.functions.name().call()
            
            logger.info(f"Initialized monitor for {self.name} ({self.symbol})")
            
        except Exception as e:
            logger.error(f"Failed to initialize token monitor: {str(e)}")
            raise
            
    def _is_significant_transfer(self, amount: int) -> bool:
        """Check if a transfer amount is significant."""
        return format_token_amount(amount, self.decimals) >= self.min_amount
        
    def _update_address_stats(self, transfer: Dict[str, Any]):
        """Update statistics for addresses involved in the transfer."""
        from_addr = transfer["from"].lower()
        to_addr = transfer["to"].lower()
        amount = transfer["value"]
        
        # Update sender stats
        self.address_stats[from_addr]["total_volume"] += amount
        self.address_stats[from_addr]["transfer_count"] += 1
        self.address_stats[from_addr]["last_transfer"] = datetime.now()
        
        # Update receiver stats
        self.address_stats[to_addr]["total_volume"] += amount
        self.address_stats[to_addr]["transfer_count"] += 1
        self.address_stats[to_addr]["last_transfer"] = datetime.now()
        
        # Track protocol interactions
        if is_known_protocol(from_addr):
            self.address_stats[to_addr]["protocol_interactions"] += 1
        if is_known_protocol(to_addr):
            self.address_stats[from_addr]["protocol_interactions"] += 1
            
    def _cleanup_old_data(self):
        """Remove data older than the time window."""
        cutoff_time = datetime.now() - timedelta(seconds=self.time_window)
        
        # Clean up transfers
        self.transfers = [
            t for t in self.transfers
            if datetime.fromtimestamp(t["block_number"]) > cutoff_time
        ]
        
        # Clean up address stats
        for addr in list(self.address_stats.keys()):
            if self.address_stats[addr]["last_transfer"] < cutoff_time:
                del self.address_stats[addr]
                
    def analyze_patterns(self) -> List[Dict[str, Any]]:
        """
        Analyze transfer patterns to identify potential alpha signals.
        
        Returns:
            List of potential alpha signals
        """
        self._cleanup_old_data()
        signals = []
        
        for addr, stats in self.address_stats.items():
            # Calculate transfer frequency
            if stats["transfer_count"] > 0:
                time_diff = (datetime.now() - stats["last_transfer"]).total_seconds()
                frequency = stats["transfer_count"] / (time_diff / 3600)  # transfers per hour
                
                # Identify potential signals
                if (
                    frequency > 10  # High frequency
                    and stats["protocol_interactions"] > 0  # Protocol interactions
                    and format_token_amount(stats["total_volume"], self.decimals) > self.min_amount * 5  # Large volume
                ):
                    signals.append({
                        "address": addr,
                        "frequency": frequency,
                        "total_volume": format_token_amount(stats["total_volume"], self.decimals),
                        "protocol_interactions": stats["protocol_interactions"],
                        "last_transfer": stats["last_transfer"].isoformat()
                    })
                    
        return signals
        
    async def process_transfer_event(self, event: Dict[str, Any]):
        """Process a transfer event and update tracking data."""
        transfer = parse_transfer_event(event)
        
        if self._is_significant_transfer(transfer["value"]):
            self.transfers.append(transfer)
            self._update_address_stats(transfer)
            
            # Log significant transfers
            logger.info(
                f"Significant transfer detected: {format_token_amount(transfer['value'], self.decimals)} "
                f"{self.symbol} from {transfer['from']} to {transfer['to']}"
            )
            
    async def get_token_info(self) -> Dict[str, Any]:
        """Get current token information."""
        return {
            "address": self.token_address,
            "name": self.name,
            "symbol": self.symbol,
            "decimals": self.decimals,
            "total_transfers": len(self.transfers),
            "unique_addresses": len(self.address_stats)
        } 