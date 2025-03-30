"""
Chain information utilities for the Token Movement Strategy.
"""
from typing import Dict, Optional

class ChainInfo:
    """
    Utility class for chain-related information and operations.
    """
    
    # Average block times for different chains (in seconds)
    BLOCK_TIMES = {
        1: 15,    # Ethereum: ~15 seconds
        56: 3,    # BSC: ~3 seconds
        137: 2,    # Polygon: ~2 seconds
        10: 2,     # Optimism: ~2 seconds
        42161: 0.25,  # Arbitrum: ~0.25 seconds
        43114: 2,  # Avalanche: ~2 seconds
        250: 1,    # Fantom: ~1 second
        25: 6,     # Cronos: ~6 seconds
        100: 5,    # Gnosis Chain: ~5 seconds
    }
    
    # Default block time for chains not in the list
    DEFAULT_BLOCK_TIME = 15  # seconds
    
    # Chain names mapping
    CHAIN_NAMES = {
        1: "Ethereum",
        56: "Binance Smart Chain",
        137: "Polygon",
        10: "Optimism",
        42161: "Arbitrum",
        43114: "Avalanche",
        250: "Fantom",
        25: "Cronos",
        100: "Gnosis Chain",
        42220: "Celo",
        1313161554: "Aurora",
        8217: "Klaytn",
        1284: "Moonbeam",
        1285: "Moonriver",
        128: "Huobi ECO Chain"
    }
    
    # Native token symbols by chain
    NATIVE_SYMBOLS = {
        1: 'ETH',    # Ethereum
        56: 'BNB',   # Binance Smart Chain
        137: 'MATIC', # Polygon
        10: 'ETH',   # Optimism
        42161: 'ETH', # Arbitrum
        43114: 'AVAX' # Avalanche
    }
    
    # Native token decimals by chain
    NATIVE_DECIMALS = {
        1: 18,     # Ethereum (ETH)
        56: 18,    # Binance Smart Chain (BNB)
        137: 18,   # Polygon (MATIC)
        10: 18,    # Optimism (ETH)
        42161: 18, # Arbitrum (ETH)
        43114: 18  # Avalanche (AVAX)
    }
    
    @classmethod
    def get_block_time(cls, chain_id: int) -> float:
        """
        Get the average block time for a chain.
        
        Args:
            chain_id: Blockchain ID
            
        Returns:
            float: Average block time in seconds
        """
        return cls.BLOCK_TIMES.get(chain_id, cls.DEFAULT_BLOCK_TIME)
    
    @classmethod
    def estimate_time_from_blocks(cls, chain_id: int, block_diff: int) -> int:
        """
        Estimate time in seconds based on block difference.
        
        Args:
            chain_id: Blockchain ID
            block_diff: Number of blocks
            
        Returns:
            int: Estimated time in seconds
        """
        block_time = cls.get_block_time(chain_id)
        return int(block_diff * block_time)
    
    @classmethod
    def estimate_blocks_from_time(cls, chain_id: int, seconds: int) -> int:
        """
        Estimate number of blocks based on time in seconds.
        
        Args:
            chain_id: Blockchain ID
            seconds: Time in seconds
            
        Returns:
            int: Estimated number of blocks
        """
        block_time = cls.get_block_time(chain_id)
        return max(1, int(seconds / block_time))
    
    @classmethod
    def get_chain_name(cls, chain_id: int) -> str:
        """
        Get human-readable chain name for a chain ID.
        
        Args:
            chain_id: Blockchain ID
            
        Returns:
            str: Human-readable chain name
        """
        return cls.CHAIN_NAMES.get(chain_id, f"Chain {chain_id}")
    
    @classmethod
    def get_native_symbol(cls, chain_id: int) -> str:
        """
        Get the native token symbol for a chain.
        
        Args:
            chain_id: Blockchain ID
            
        Returns:
            str: Native token symbol
        """
        return cls.NATIVE_SYMBOLS.get(chain_id, 'Native')
    
    @classmethod
    def get_native_decimals(cls, chain_id: int) -> int:
        """
        Get the native token decimals for a chain.
        
        Args:
            chain_id: Blockchain ID
            
        Returns:
            int: Number of decimals for the native token
        """
        return cls.NATIVE_DECIMALS.get(chain_id, 18)
