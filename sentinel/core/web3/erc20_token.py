from typing import Optional, List, Dict, Any, Union
from web3 import Web3
from web3.contract import Contract
from web3.types import Address, ChecksumAddress
from functools import cached_property
from web3.exceptions import BadFunctionCallOutput

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
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    # Balance and allowance functions
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    # Transfer and approval functions
    {
        "constant": False,
        "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [{"name": "_from", "type": "address"}, {"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "transferFrom",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function"
    },
    # Standard events
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"}
        ],
        "name": "Transfer",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "owner", "type": "address"},
            {"indexed": True, "name": "spender", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"}
        ],
        "name": "Approval",
        "type": "event"
    }
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
            return f"???"
        
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
        return raw_balance / (10 ** self.decimals)
        
    def get_transfer_events(
        self, 
        from_block: int, 
        to_block: Union[int, str] = 'latest',
        from_address: Optional[Union[str, List[str]]] = None,
        to_address: Optional[Union[str, List[str]]] = None
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
        # Prepare filter parameters
        filter_params = {
            'fromBlock': from_block,
            'toBlock': to_block,
            'address': self.address
        }
        
        # Create argument filters
        argument_filters = {}
        
        # Add from address filter if provided
        if from_address:
            if isinstance(from_address, str):
                if Web3.is_address(from_address):
                    argument_filters['from'] = Web3.to_checksum_address(from_address)
            elif isinstance(from_address, list) and len(from_address) > 0:
                valid_addresses = [
                    Web3.to_checksum_address(addr) for addr in from_address 
                    if Web3.is_address(addr)
                ]
                if valid_addresses:
                    argument_filters['from'] = valid_addresses
        
        # Add to address filter if provided
        if to_address:
            if isinstance(to_address, str):
                if Web3.is_address(to_address):
                    argument_filters['to'] = Web3.to_checksum_address(to_address)
            elif isinstance(to_address, list) and len(to_address) > 0:
                valid_addresses = [
                    Web3.to_checksum_address(addr) for addr in to_address 
                    if Web3.is_address(addr)
                ]
                if valid_addresses:
                    argument_filters['to'] = valid_addresses
        
        try:
            # First, try using the getLogs method directly
            event_signature_hash = self.web3.keccak(
                text="Transfer(address,address,uint256)"
            ).hex()
            
            logs_filter = {
                'fromBlock': from_block,
                'toBlock': to_block,
                'address': self.address,
                'topics': [event_signature_hash]
            }
            
            # Add from address filter if provided
            if 'from' in argument_filters:
                addresses = argument_filters['from']
                if isinstance(addresses, list):
                    # If it's a list, we need to match any of them
                    logs_filter['topics'].append([
                        self._encode_address_for_topic(addr) for addr in addresses
                    ])
                else:
                    logs_filter['topics'].append(self._encode_address_for_topic(addresses))
            else:
                # If no filter, match all addresses
                logs_filter['topics'].append(None)
                
            # Add to address filter if provided
            if 'to' in argument_filters:
                addresses = argument_filters['to']
                if isinstance(addresses, list):
                    logs_filter['topics'].append([
                        self._encode_address_for_topic(addr) for addr in addresses
                    ])
                else:
                    logs_filter['topics'].append(self._encode_address_for_topic(addresses))
            
            logs = self.web3.eth.get_logs(logs_filter)
            
            # Process the logs into event format
            events = []
            for log in logs:
                # Extract data
                log_data = log['data']
                topics = log['topics']
                
                # Decode event data (value is the only non-indexed parameter)
                value = int(log_data, 16)
                
                # Create event dictionary
                event = {
                    'event': 'Transfer',
                    'logIndex': log['logIndex'],
                    'transactionIndex': log['transactionIndex'],
                    'transactionHash': log['transactionHash'].hex(),
                    'blockHash': log['blockHash'].hex(),
                    'blockNumber': log['blockNumber'],
                    'address': log['address'],
                    'args': {
                        'from': Web3.to_checksum_address('0x' + topics[1].hex()[-40:]),
                        'to': Web3.to_checksum_address('0x' + topics[2].hex()[-40:]),
                        'value': value
                    }
                }
                events.append(event)
                
            return events
                
        except Exception as e:
            logger.warning(f"Error getting logs directly, falling back to contract events API: {e}")
            
            try:
                # Fallback to using the contract events API
                transfer_filter = self.contract.events.Transfer.create_filter(
                    fromBlock=from_block,
                    toBlock=to_block,
                    argument_filters=argument_filters
                )
                
                return transfer_filter.get_all_entries()
            except Exception as e:
                logger.error(f"Error getting transfer events for token {self.address}: {e}")
                return []
    
    def _encode_address_for_topic(self, address: str) -> str:
        """Helper to encode address for event topic filter"""
        return '0x' + '0' * 24 + address[2:].lower()
    
    def format_transfer_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format a Transfer event for easier reading
        
        Args:
            event: Raw event data
            
        Returns:
            Dict[str, Any]: Formatted event data
        """
        args = event['args']
        
        # Format the transfer amount (account for token decimals)
        formatted_value = args['value'] / (10 ** self.decimals)
        
        return {
            'token': {
                'address': self.address,
                'name': self.name,
                'symbol': self.symbol
            },
            'from': args['from'],
            'to': args['to'],
            'value': args['value'],  # Raw value
            'formatted_value': formatted_value,  # Formatted value
            'transaction_hash': event['transactionHash'].hex(),
            'block_number': event['blockNumber'],
            'log_index': event['logIndex']
        } 