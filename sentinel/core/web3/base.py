from typing import Any, Dict

from web3 import Web3

# Common ERC20 event signatures
TRANSFER_EVENT_SIGNATURE = "Transfer(address,address,uint256)"
TRANSFER_EVENT_TOPIC = Web3.keccak(text=TRANSFER_EVENT_SIGNATURE).hex()

# Common ERC20 ABI
ERC20_ABI = [
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
]

# Known DeFi protocol addresses (example)
KNOWN_DEFI_PROTOCOLS: Dict[str, str] = {
    "uniswap_v2_router": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
    "uniswap_v3_router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
    "sushiswap_router": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
    "aave_v2_lending_pool": "0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9",
    "curve_swap_router": "0x8e764bE4288B842791989DB5B8ec067279829809",
}


def format_token_amount(amount: int, decimals: int) -> float:
    """Format token amount from wei to human readable format."""
    return amount / (10**decimals)


def parse_transfer_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse a Transfer event into a human readable format.

    Args:
        event: The raw event data from Web3

    Returns:
        Dict containing parsed event data
    """
    return {
        "from": event["args"]["from"],
        "to": event["args"]["to"],
        "value": event["args"]["value"],
        "block_number": event["blockNumber"],
        "transaction_hash": event["transactionHash"].hex(),
    }


def is_known_protocol(address: str) -> bool:
    """Check if an address is a known DeFi protocol."""
    return address.lower() in [addr.lower() for addr in KNOWN_DEFI_PROTOCOLS.values()]
