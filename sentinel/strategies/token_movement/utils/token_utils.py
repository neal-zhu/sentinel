"""
Token utility functions for the Token Movement Strategy.
"""
from typing import Dict, List, Optional, Set
from sentinel.strategies.token_movement.utils.chain_info import ChainInfo

class TokenUtils:
    """
    Utility class for token-related operations and checks.
    """
    
    # Common stablecoin symbols
    STABLECOIN_SYMBOLS = ['USDT', 'USDC', 'DAI', 'BUSD', 'TUSD', 'UST', 'GUSD', 'USDP', 'FRAX']
    
    # Well-known stablecoin addresses by chain
    STABLECOIN_ADDRESSES = {
        1: [  # Ethereum
            '0xdac17f958d2ee523a2206206994597c13d831ec7',  # USDT
            '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',  # USDC
            '0x6b175474e89094c44da98b954eedeac495271d0f',  # DAI
            '0x4fabb145d64652a948d72533023f6e7a623c7c53',  # BUSD
            '0x0000000000085d4780b73119b644ae5ecd22b376',  # TUSD
            '0x956f47f50a910163d8bf957cf5846d573e7f87ca',  # FEI
            '0xa47c8bf37f92abed4a126bda807a7b7498661acd',  # WUST
            '0x853d955acef822db058eb8505911ed77f175b99e',  # FRAX
        ],
        56: [  # BSC
            '0x55d398326f99059ff775485246999027b3197955',  # BSC-USDT
            '0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d',  # BSC-USDC
            '0x1af3f329e8be154074d8769d1ffa4ee058b1dbc3',  # BSC-DAI
            '0xe9e7cea3dedca5984780bafc599bd69add087d56',  # BUSD
        ],
        137: [  # Polygon
            '0xc2132d05d31c914a87c6611c10748aeb04b58e8f',  # USDT
            '0x2791bca1f2de4661ed88a30c99a7a9449aa84174',  # USDC
            '0x8f3cf7ad23cd3cadbd9735aff958023239c6a063',  # DAI
            '0x9C9e5fD8bbc25984B178FdCE6117Defa39d2db39',  # BUSD
        ],
        10: [  # Optimism
            '0x94b008aa00579c1307b0ef2c499ad98a8ce58e58',  # USDT
            '0x7f5c764cbc14f9669b88837ca1490cca17c31607',  # USDC
            '0xda10009cbd5d07dd0cecc66161fc93d7c9000da1',  # DAI
        ],
        42161: [  # Arbitrum
            '0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9',  # USDT
            '0xff970a61a04b1ca14834a43f5de4533ebddb5cc8',  # USDC
            '0xda10009cbd5d07dd0cecc66161fc93d7c9000da1',  # DAI
        ]
    }
    
    # Common DEX pair tokens
    COMMON_DEX_TOKENS = ['WETH', 'WBTC', 'USDT', 'USDC', 'DAI', 'WBNB', 'WMATIC']
    
    @classmethod
    def is_stablecoin(cls, chain_id: int, token_address: str, token_symbol: str) -> bool:
        """
        Determine if a token is a stablecoin.
        
        Args:
            chain_id: Blockchain ID
            token_address: Token contract address
            token_symbol: Token symbol
            
        Returns:
            bool: Whether the token is a stablecoin
        """
        # Check by symbol
        if token_symbol in cls.STABLECOIN_SYMBOLS:
            return True
            
        # Check by address
        if chain_id in cls.STABLECOIN_ADDRESSES and token_address:
            if token_address.lower() in [addr.lower() for addr in cls.STABLECOIN_ADDRESSES[chain_id]]:
                return True
                
        return False
    
    @classmethod
    def is_common_dex_token(cls, token_symbol: str) -> bool:
        """
        Check if a token is commonly used in DEX pairs.
        
        Args:
            token_symbol: Token symbol
            
        Returns:
            bool: Whether the token is commonly used in DEX pairs
        """
        return token_symbol in cls.COMMON_DEX_TOKENS
    
    @classmethod
    def get_token_symbol(cls, chain_id: int, token_address: str, token_symbols_cache: Dict[str, str] = None) -> str:
        """
        Get the symbol for a token.
        
        Args:
            chain_id: Blockchain ID
            token_address: Token contract address
            token_symbols_cache: Optional cache of token symbols
            
        Returns:
            str: Token symbol or 'Unknown'
        """
        # Return native token symbol if this is a native token transfer
        if not token_address or token_address == '0x0000000000000000000000000000000000000000':
            return ChainInfo.get_native_symbol(chain_id)
            
        # Check cache if provided
        if token_symbols_cache:
            token_key = f"{chain_id}:{token_address.lower()}"
            if token_key in token_symbols_cache:
                return token_symbols_cache[token_key]
                
        # For now, just return a placeholder
        # In a real implementation, you'd query the token contract
        return 'ERC20'
    
    @classmethod
    def format_token_value(cls, chain_id: int, token_address: str, value: int, 
                          token_decimals_cache: Dict[str, int] = None) -> float:
        """
        Format a token value using the correct decimals.
        
        Args:
            chain_id: Blockchain ID
            token_address: Token contract address
            value: Raw token value
            token_decimals_cache: Optional cache of token decimals
            
        Returns:
            float: Formatted token value
        """
        # If this is a native token transfer, use default decimals
        if not token_address or token_address == '0x0000000000000000000000000000000000000000':
            decimals = ChainInfo.get_native_decimals(chain_id)
            return float(value) / (10 ** decimals)
            
        # Check cache if provided
        if token_decimals_cache:
            token_key = f"{chain_id}:{token_address.lower()}"
            if token_key in token_decimals_cache:
                decimals = token_decimals_cache[token_key]
                return float(value) / (10 ** decimals)
                
        # Default to 18 decimals for most ERC20 tokens
        decimals = 18
        return float(value) / (10 ** decimals)
