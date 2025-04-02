from functools import cached_property
from typing import Any, Dict, List, Optional, Union

from web3 import AsyncWeb3, Web3
from web3.exceptions import BadFunctionCallOutput
from web3.types import FilterParams

from sentinel.logger import logger

# Standard ERC20 ABI - contains necessary functions and events
ERC20_ABI = [
    # Basic information functions
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    # Balance and allowance functions
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    # Transfer and approval functions
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_from", "type": "address"},
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transferFrom",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # Standard events
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "owner", "type": "address"},
            {"indexed": True, "name": "spender", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Approval",
        "type": "event",
    },
]


class ERC20Token:
    """
    ERC20 Token Interface
    Simplified interface for interacting with ERC20 token contracts
    """

    def __init__(self, web3: Web3, address: str):
        """
        Initialize ERC20 Token interface

        Args:
            web3: Web3 instance
            address: Token contract address
        """
        if not web3.is_address(address):
            raise ValueError(f"Invalid ERC20 token address: {address}")

        self.web3 = web3
        self.address = web3.to_checksum_address(address)
        self.contract = web3.eth.contract(address=self.address, abi=ERC20_ABI)

        # Cache basic information
        self._name = None
        self._symbol = None
        self._decimals = None

    @cached_property
    def name(self) -> str:
        """Get token name"""
        try:
            return self.contract.functions.name().call()
        except (BadFunctionCallOutput, Exception) as e:
            logger.warning(f"Error getting token name for {self.address}: {e}")
            return f"Unknown ({self.address[:6]}...{self.address[-4:]})"

    @cached_property
    def symbol(self) -> str:
        """Get token symbol"""
        try:
            return self.contract.functions.symbol().call()
        except (BadFunctionCallOutput, Exception) as e:
            logger.warning(f"Error getting token symbol for {self.address}: {e}")
            return "???"

    @cached_property
    def decimals(self) -> int:
        """Get token decimals"""
        try:
            return self.contract.functions.decimals().call()
        except (BadFunctionCallOutput, Exception) as e:
            logger.warning(f"Error getting token decimals for {self.address}: {e}")
            return 18  # Assume default 18 decimals

    @property
    def total_supply(self) -> int:
        """Get token total supply"""
        try:
            return self.contract.functions.totalSupply().call()
        except (BadFunctionCallOutput, Exception) as e:
            logger.error(f"Error getting total supply for {self.address}: {e}")
            return 0

    def balance_of(self, address: str) -> int:
        """
        Get token balance for an address

        Args:
            address: Address to query balance for

        Returns:
            int: Raw token balance (unformatted)
        """
        address = self.web3.to_checksum_address(address)
        return self.contract.functions.balanceOf(address).call()

    def formatted_balance_of(self, address: str) -> float:
        """
        Get formatted token balance for an address

        Args:
            address: Address to query balance for

        Returns:
            float: Formatted token balance (accounting for decimals)
        """
        raw_balance = self.balance_of(address)
        return raw_balance / (10**self.decimals)

    def get_transfer_events(
        self,
        from_block: int,
        to_block: Union[int, str] = "latest",
        from_address: Optional[Union[str, List[str]]] = None,
        to_address: Optional[Union[str, List[str]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get transfer events for the token

        Args:
            from_block: Starting block
            to_block: Ending block or 'latest'
            from_address: Filter by sender address(es)
            to_address: Filter by receiver address(es)

        Returns:
            List[Dict[str, Any]]: List of transfer events
        """
        # Create argument filters
        argument_filters = {}

        def fill_address_filter(key: str, addresses: Optional[Union[str, List[str]]]):
            if isinstance(addresses, str):
                if Web3.is_address(addresses):
                    argument_filters[key] = Web3.to_checksum_address(addresses)
            elif isinstance(addresses, list) and len(addresses) > 0:
                valid_addresses = [
                    Web3.to_checksum_address(addr)
                    for addr in addresses
                    if Web3.is_address(addr)
                ]
                if valid_addresses:
                    argument_filters[key] = valid_addresses

        # Add from address filter if provided
        fill_address_filter("from", from_address)

        # Add to address filter if provided
        fill_address_filter("to", to_address)

        try:
            # First, try using the getLogs method directly
            event_signature_hash = self.web3.keccak(
                text="Transfer(address,address,uint256)"
            ).hex()

            logs_filter = FilterParams(
                fromBlock=from_block,
                toBlock=to_block,
                address=self.address,
                topics=[event_signature_hash],
            )

            # Add from address filter if provided
            if "from" in argument_filters:
                addresses = argument_filters["from"]
                if isinstance(addresses, list):
                    # If it's a list, we need to match any of them
                    logs_filter["topics"].append(
                        [self._encode_address_for_topic(addr) for addr in addresses]
                    )
                else:
                    logs_filter["topics"].append(
                        self._encode_address_for_topic(addresses)
                    )
            else:
                # If no filter, match all addresses
                logs_filter["topics"].append(None)

            # Add to address filter if provided
            if "to" in argument_filters:
                addresses = argument_filters["to"]
                if isinstance(addresses, list):
                    logs_filter["topics"].append(
                        [self._encode_address_for_topic(addr) for addr in addresses]
                    )
                else:
                    logs_filter["topics"].append(
                        self._encode_address_for_topic(addresses)
                    )

            logs = self.web3.eth.get_logs(logs_filter)

            # Process the logs into event format
            events = []
            for log in logs:
                # Extract data
                log_data = log["data"]
                topics = log["topics"]

                # Decode event data (value is the only non-indexed parameter)
                value = int(log_data, 16)

                # Create event dictionary
                event = {
                    "event": "Transfer",
                    "logIndex": log["logIndex"],
                    "transactionIndex": log["transactionIndex"],
                    "transactionHash": log["transactionHash"].hex(),
                    "blockHash": log["blockHash"].hex(),
                    "blockNumber": log["blockNumber"],
                    "address": log["address"],
                    "args": {
                        "from": Web3.to_checksum_address("0x" + topics[1].hex()[-40:]),
                        "to": Web3.to_checksum_address("0x" + topics[2].hex()[-40:]),
                        "value": value,
                    },
                }
                events.append(event)

            return events

        except Exception as e:
            logger.error(
                f"Error getting logs directly, falling back to contract events API: {e}"
            )
            return []

    def _encode_address_for_topic(self, address: str) -> str:
        """Helper to encode address for event topic filter"""
        return "0x" + "0" * 24 + address[2:].lower()

    def format_transfer_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format a Transfer event for easier reading

        Args:
            event: Raw event data

        Returns:
            Dict[str, Any]: Formatted event data
        """
        args = event["args"]

        # Format the transfer amount (account for token decimals)
        formatted_value = args["value"] / (10**self.decimals)

        return {
            "token": {
                "address": self.address,
                "name": self.name,
                "symbol": self.symbol,
            },
            "from": args["from"],
            "to": args["to"],
            "value": args["value"],  # Raw value
            "formatted_value": formatted_value,  # Formatted value
            "transaction_hash": event["transactionHash"].hex(),
            "block_number": event["blockNumber"],
            "log_index": event["logIndex"],
        }


class AsyncERC20Token:
    """
    Async ERC20 Token Interface
    Simplified interface for interacting with ERC20 token contracts asynchronously
    """

    def __init__(self, web3: "AsyncWeb3", address: str):
        """
        Initialize Async ERC20 Token interface

        Args:
            web3: AsyncWeb3 instance
            address: Token contract address
        """
        if not web3.is_address(address):
            raise ValueError(f"Invalid ERC20 token address: {address}")

        self.web3 = web3
        self.address = web3.to_checksum_address(address)
        self.contract = web3.eth.contract(address=self.address, abi=ERC20_ABI)

        # Cache for token information
        self._name = None
        self._symbol = None
        self._decimals = None

    async def _init_properties(self):
        """Initialize properties asynchronously"""
        if self._name is None:
            try:
                self._name = await self.contract.functions.name().call()
            except Exception as e:
                logger.warning(f"Error getting token name for {self.address}: {e}")
                self._name = f"Unknown ({self.address[:6]}...{self.address[-4:]})"

        if self._symbol is None:
            try:
                self._symbol = await self.contract.functions.symbol().call()
            except Exception as e:
                logger.warning(f"Error getting token symbol for {self.address}: {e}")
                self._symbol = "???"

        if self._decimals is None:
            try:
                self._decimals = await self.contract.functions.decimals().call()
            except Exception as e:
                logger.warning(f"Error getting token decimals for {self.address}: {e}")
                self._decimals = 18  # Assume default 18 decimals

    @property
    def name(self) -> str:
        """Get token name (cached)"""
        return self._name

    @property
    def symbol(self) -> str:
        """Get token symbol (cached)"""
        return self._symbol

    @property
    def decimals(self) -> int:
        """Get token decimals (cached)"""
        return self._decimals

    async def total_supply(self) -> int:
        """Get token total supply"""
        try:
            return await self.contract.functions.totalSupply().call()
        except Exception as e:
            logger.error(f"Error getting total supply for {self.address}: {e}")
            return 0

    async def balance_of(self, address: str) -> int:
        """
        Get token balance for an address

        Args:
            address: Address to query balance for

        Returns:
            int: Raw token balance (unformatted)
        """
        address = self.web3.to_checksum_address(address)
        return await self.contract.functions.balanceOf(address).call()

    async def formatted_balance_of(self, address: str) -> float:
        """
        Get formatted token balance for an address

        Args:
            address: Address to query balance for

        Returns:
            float: Formatted token balance (accounting for decimals)
        """
        await self._init_properties()  # Ensure decimals are loaded
        raw_balance = await self.balance_of(address)
        return raw_balance / (10**self._decimals)

    async def get_transfer_events(
        self,
        from_block: int,
        to_block: Union[int, str] = "latest",
        from_address: Optional[Union[str, List[str]]] = None,
        to_address: Optional[Union[str, List[str]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get transfer events for the token

        Args:
            from_block: Starting block
            to_block: Ending block or 'latest'
            from_address: Filter by sender address(es)
            to_address: Filter by receiver address(es)

        Returns:
            List[Dict[str, Any]]: List of transfer events
        """
        # Create argument filters
        argument_filters = {}

        def fill_address_filter(key: str, addresses: Optional[Union[str, List[str]]]):
            if isinstance(addresses, str):
                if self.web3.is_address(addresses):
                    argument_filters[key] = self.web3.to_checksum_address(addresses)
            elif isinstance(addresses, list) and len(addresses) > 0:
                valid_addresses = [
                    self.web3.to_checksum_address(addr)
                    for addr in addresses
                    if self.web3.is_address(addr)
                ]
                if valid_addresses:
                    argument_filters[key] = valid_addresses

        # Add from address filter if provided
        fill_address_filter("from", from_address)

        # Add to address filter if provided
        fill_address_filter("to", to_address)

        try:
            # First, try using the getLogs method directly
            event_signature_hash = self.web3.keccak(
                text="Transfer(address,address,uint256)"
            ).hex()

            logs_filter = {
                "from_block": from_block,
                "to_block": to_block,
                "address": self.address,
                "topics": [event_signature_hash],
            }

            # Add from address filter if provided
            if "from" in argument_filters:
                addresses = argument_filters["from"]
                if isinstance(addresses, list):
                    # If it's a list, we need to match any of them
                    logs_filter["topics"].append(
                        [self._encode_address_for_topic(addr) for addr in addresses]
                    )
                else:
                    logs_filter["topics"].append(
                        self._encode_address_for_topic(addresses)
                    )
            else:
                # If no filter, match all addresses
                logs_filter["topics"].append(None)

            # Add to address filter if provided
            if "to" in argument_filters:
                addresses = argument_filters["to"]
                if isinstance(addresses, list):
                    logs_filter["topics"].append(
                        [self._encode_address_for_topic(addr) for addr in addresses]
                    )
                else:
                    logs_filter["topics"].append(
                        self._encode_address_for_topic(addresses)
                    )

            logs = await self.web3.eth.get_logs(logs_filter)

            # Process the logs into event format
            events = []
            for log in logs:
                # Extract data
                log_data = log["data"]
                topics = log["topics"]

                # Decode event data (value is the only non-indexed parameter)
                value = int(log_data, 16)

                # Create event dictionary
                event = {
                    "event": "Transfer",
                    "logIndex": log["logIndex"],
                    "transactionIndex": log["transactionIndex"],
                    "transactionHash": log["transactionHash"].hex(),
                    "blockHash": log["blockHash"].hex(),
                    "blockNumber": log["blockNumber"],
                    "address": log["address"],
                    "args": {
                        "from": self.web3.to_checksum_address(
                            "0x" + topics[1].hex()[-40:]
                        ),
                        "to": self.web3.to_checksum_address(
                            "0x" + topics[2].hex()[-40:]
                        ),
                        "value": value,
                    },
                }
                events.append(event)

            return events

        except Exception as e:
            logger.error(f"Error getting transfer logs: {e}")
            return []

    def _encode_address_for_topic(self, address: str) -> str:
        """Helper to encode address for event topic filter"""
        return "0x" + "0" * 24 + address[2:].lower()

    async def format_transfer_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format a Transfer event for easier reading

        Args:
            event: Raw event data

        Returns:
            Dict[str, Any]: Formatted event data
        """
        await self._init_properties()  # Ensure name, symbol, decimals are loaded
        args = event["args"]

        # Format the transfer amount (account for token decimals)
        formatted_value = args["value"] / (10**self._decimals)

        return {
            "token": {
                "address": self.address,
                "name": self._name,
                "symbol": self._symbol,
            },
            "from": args["from"],
            "to": args["to"],
            "value": args["value"],  # Raw value
            "formatted_value": formatted_value,  # Formatted value
            "transaction_hash": event["transactionHash"].hex(),
            "block_number": event["blockNumber"],
            "log_index": event["logIndex"],
        }
