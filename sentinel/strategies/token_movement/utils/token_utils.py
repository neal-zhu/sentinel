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
    
    # Common DEX pair tokens - expanding to include more tokens important for DEX trading and arbitrage
    COMMON_DEX_TOKENS = [
        # Base assets and wrapped versions
        'ETH', 'WETH', 'BTC', 'WBTC', 'BNB', 'WBNB', 'MATIC', 'WMATIC', 'AVAX', 'WAVAX',
        # Stablecoins
        'USDT', 'USDC', 'DAI', 'BUSD', 'TUSD', 'FRAX', 'USDP', 'GUSD', 'LUSD', 'MIM',
        # Common DeFi tokens
        'UNI', 'SUSHI', 'AAVE', 'CRV', 'BAL', 'COMP', 'MKR', 'SNX', 'YFI', '1INCH',
        # Liquid staking tokens
        'STETH', 'WSTETH', 'RETH', 'CBETH', 'SFRXETH', 'ANKR', 'STMATIC',
        # LSD liquidity tokens
        'ETHX', 'SWETH', 'ETH2X-FLI'
    ]

    # High interest tokens with significant arbitrage/trading opportunities
    HIGH_INTEREST_TOKENS = {
        1: [  # Ethereum
            '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',  # WETH
            '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599',  # WBTC
            '0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0',  # wstETH
            '0xae7ab96520de3a18e5e111b5eaab095312d7fe84',  # stETH
            '0xae78736cd615f374d3085123a210448e74fc6393',  # rETH
            '0xbe9895146f7af43049ca1c1ae358b0541ea49704',  # cbETH
            '0x5e8422345238f34275888049021821e8e08caa1f',  # frxETH
            '0xac3e018457b222d93114458476f3e3416abbe38f',  # sfrxETH
            '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',  # USDC
            '0xdac17f958d2ee523a2206206994597c13d831ec7',  # USDT
            '0x6b175474e89094c44da98b954eedeac495271d0f',  # DAI
            '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984',  # UNI
            '0xd533a949740bb3306d119cc777fa900ba034cd52',  # CRV
            '0x4d224452801aced8b2f0aebe155379bb5d594381',  # APE
            '0xbb0e17ef65f82ab018d8edd776e8dd940327b28b',  # AXS
        ],
        # Add other chains as needed
    }
    
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
    def is_high_interest_token(cls, chain_id: int, token_address: str) -> bool:
        """
        Check if a token is in our high interest list for arbitrage/trading opportunities.
        
        Args:
            chain_id: Blockchain ID
            token_address: Token contract address
            
        Returns:
            bool: Whether the token is in our high interest list
        """
        if not token_address or not isinstance(chain_id, int):
            return False
            
        if chain_id not in cls.HIGH_INTEREST_TOKENS:
            return False
            
        return token_address.lower() in [addr.lower() for addr in cls.HIGH_INTEREST_TOKENS[chain_id]]
    
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
