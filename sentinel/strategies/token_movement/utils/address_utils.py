"""
Address utility functions for the Token Movement Strategy.
"""
from typing import Dict, List


class AddressUtils:
    """
    Utility class for address-related operations and checks.
    """

    # Common DEX and protocol addresses by chain
    KNOWN_DEXES = {
        1: [  # Ethereum
            "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",  # Uniswap V2 Router
            "0xe592427a0aece92de3edee1f18e0157c05861564",  # Uniswap V3 Router
            "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f",  # SushiSwap Router
            "0x1111111254fb6c44bac0bed2854e76f90643097d",  # 1inch Router
            "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9",  # Aave v2
            "0x398ec7346dcd622edc5ae82352f02be94c62d119",  # Aave v1
            "0x3d9819210a31b4961b30ef54be2aed79b9c9cd3b",  # Compound
        ],
        56: [  # Binance Smart Chain
            "0x05ff2b0db69458a0750badebc4f9e13add608c7f",  # PancakeSwap Router v1
            "0x1111111254fb6c44bac0bed2854e76f90643097d",  # 1inch Router
        ],
        137: [  # Polygon
            "0xa5e0829caced8ffdd4de3c43696c57f7d7a678ff",  # QuickSwap Router
            "0x1111111254fb6c44bac0bed2854e76f90643097d",  # 1inch Router
            "0x8954afa98594b838bda56fe4c12a09d7739d179b",  # Sushi Router
        ],
        42161: [  # Arbitrum
            "0x1111111254fb6c44bac0bed2854e76f90643097d",  # 1inch Router
            "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f",  # SushiSwap Router
        ],
        10: [  # Optimism
            "0x1111111254fb6c44bac0bed2854e76f90643097d",  # 1inch Router
            "0xe592427a0aece92de3edee1f18e0157c05861564",  # Uniswap V3 Router
        ],
    }

    # Common patterns for contract addresses
    CONTRACT_PREFIXES = [
        "0x7a250d5",  # Uniswap Router
        "0xe592427",  # Uniswap V3
        "0x111111",  # 1inch
        "0xa5e0829",  # QuickSwap
        "0x68b3465",  # Uniswap V3 Router 2
        "0xd9e1ce1",  # SushiSwap
        "0x05ff2b0",  # PancakeSwap
    ]

    @classmethod
    def is_contract_address(
        cls, address: str, known_dexes: Dict[int, List[str]] = None
    ) -> bool:
        """
        Check if an address is likely a contract address.

        Args:
            address: Ethereum address to check
            known_dexes: Optional dictionary of known DEX addresses by chain

        Returns:
            bool: Whether the address is likely a contract
        """
        # This is a simplified heuristic - in a real implementation you would query the blockchain
        # or use a database of known contracts

        # Check if address starts with any known contract prefix
        address_lower = address.lower()
        for prefix in cls.CONTRACT_PREFIXES:
            if address_lower.startswith(prefix.lower()):
                return True

        # Check if address is in our known DEX list for any chain
        dexes = known_dexes or cls.KNOWN_DEXES
        for chain_id, addresses in dexes.items():
            if address_lower in [addr.lower() for addr in addresses]:
                return True

        # By default, we can't determine if it's a contract without blockchain query
        return False

    @classmethod
    def is_whitelisted_address(
        cls, chain_id: int, address: str, whitelist: Dict[str, List[str]] = None
    ) -> bool:
        """
        Check if an address is on the whitelist (typically DEXs, known protocols).

        Args:
            chain_id: Blockchain ID
            address: Address to check
            whitelist: Optional user-configured whitelist

        Returns:
            bool: Whether the address is whitelisted
        """
        # Check user-configured whitelist
        if whitelist:
            chain_str = str(chain_id)
            if chain_str in whitelist:
                if address.lower() in [a.lower() for a in whitelist[chain_str]]:
                    return True

        # Check known DEXes
        if chain_id in cls.KNOWN_DEXES:
            if address.lower() in [a.lower() for a in cls.KNOWN_DEXES[chain_id]]:
                return True

        return False

    @classmethod
    def is_watched_address(
        cls, chain_id: int, address: str, watch_addresses: Dict[str, List[str]]
    ) -> bool:
        """
        Check if the address is in the watch list for the given chain.

        Args:
            chain_id: Blockchain ID
            address: Address to check
            watch_addresses: Dictionary of watched addresses by chain

        Returns:
            bool: Whether the address is watched
        """
        if not watch_addresses:
            return False

        chain_str = str(chain_id)
        if chain_str not in watch_addresses:
            return False

        watched_addresses = [addr.lower() for addr in watch_addresses[chain_str]]
        return address.lower() in watched_addresses
