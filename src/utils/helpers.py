"""Helper functions for Fast Arbitrage"""

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timezone


def format_currency(amount: float, decimals: int = 2, symbol: str = "$") -> str:
    """Format currency amount with proper decimals and symbol
    
    Args:
        amount: Amount to format
        decimals: Number of decimal places
        symbol: Currency symbol
        
    Returns:
        Formatted currency string
    """
    if amount is None:
        return f"{symbol}0.00"
    
    # Use Decimal for precise formatting
    decimal_amount = Decimal(str(amount))
    format_str = f"{{:.{decimals}f}}"
    
    return f"{symbol}{format_str.format(float(decimal_amount))}"


def calculate_percentage_diff(value1: float, value2: float) -> float:
    """Calculate percentage difference between two values
    
    Args:
        value1: First value
        value2: Second value
        
    Returns:
        Percentage difference ((value1 - value2) / value2 * 100)
    """
    if value2 == 0:
        return float('inf') if value1 > 0 else float('-inf') if value1 < 0 else 0.0
    
    return ((value1 - value2) / value2) * 100


def calculate_funding_rate_spread(rate1: float, rate2: float) -> float:
    """Calculate funding rate spread (absolute difference)
    
    Args:
        rate1: Funding rate from exchange 1
        rate2: Funding rate from exchange 2
        
    Returns:
        Absolute difference in funding rates
    """
    return abs(rate1 - rate2)


def validate_trading_pair(symbol: str) -> bool:
    """Validate trading pair symbol format
    
    Args:
        symbol: Trading pair symbol (e.g., 'BTC-USD', 'ETH-USDT')
        
    Returns:
        True if valid format, False otherwise
    """
    # Basic pattern: BASE-QUOTE (e.g., BTC-USD, ETH-USDT)
    pattern = r'^[A-Z]{2,10}-[A-Z]{2,10}$'
    return bool(re.match(pattern, symbol.upper()))


def parse_trading_pair(symbol: str) -> Tuple[str, str]:
    """Parse trading pair into base and quote currencies
    
    Args:
        symbol: Trading pair symbol (e.g., 'BTC-USD')
        
    Returns:
        Tuple of (base, quote) currencies
        
    Raises:
        ValueError: If symbol format is invalid
    """
    if not validate_trading_pair(symbol):
        raise ValueError(f"Invalid trading pair format: {symbol}")
    
    parts = symbol.upper().split('-')
    return parts[0], parts[1]


def normalize_symbol(symbol: str, exchange: str) -> str:
    """Normalize symbol for specific exchange format
    
    Args:
        symbol: Standard symbol (e.g., 'BTC-USD')
        exchange: Exchange name ('reya', 'hyperliquid')
        
    Returns:
        Exchange-specific symbol format
    """
    base, quote = parse_trading_pair(symbol)
    
    if exchange.lower() == 'reya':
        # Reya format: BTC-rUSD
        if quote == 'USD':
            quote = 'rUSD'
        return f"{base}-{quote}"
    
    elif exchange.lower() == 'hyperliquid':
        # Hyperliquid format: just the base (BTC)
        return base
    
    else:
        # Default format
        return f"{base}-{quote}"


def get_current_timestamp() -> int:
    """Get current timestamp in milliseconds
    
    Returns:
        Current timestamp in milliseconds
    """
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def format_timestamp(timestamp: int, format_str: str = "%Y-%m-%d %H:%M:%S UTC") -> str:
    """Format timestamp to human-readable string
    
    Args:
        timestamp: Timestamp in milliseconds
        format_str: Format string for datetime
        
    Returns:
        Formatted timestamp string
    """
    dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
    return dt.strftime(format_str)


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Float value or default
    """
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers
    
    Args:
        numerator: Numerator
        denominator: Denominator
        default: Default value if division by zero
        
    Returns:
        Division result or default
    """
    try:
        return numerator / denominator if denominator != 0 else default
    except (ValueError, TypeError, ZeroDivisionError):
        return default


def round_to_precision(value: float, precision: int) -> float:
    """Round value to specified precision
    
    Args:
        value: Value to round
        precision: Number of decimal places
        
    Returns:
        Rounded value
    """
    if precision < 0:
        precision = 0
    
    decimal_value = Decimal(str(value))
    rounded = decimal_value.quantize(
        Decimal('0.' + '0' * precision),
        rounding=ROUND_HALF_UP
    )
    return float(rounded)


def calculate_position_size(
    account_balance: float,
    risk_percentage: float,
    entry_price: float,
    stop_loss_price: float
) -> float:
    """Calculate position size based on risk management
    
    Args:
        account_balance: Total account balance
        risk_percentage: Risk percentage (e.g., 0.02 for 2%)
        entry_price: Entry price
        stop_loss_price: Stop loss price
        
    Returns:
        Calculated position size
    """
    if entry_price <= 0 or stop_loss_price <= 0:
        return 0.0
    
    risk_amount = account_balance * risk_percentage
    price_diff = abs(entry_price - stop_loss_price)
    
    if price_diff == 0:
        return 0.0
    
    position_size = risk_amount / price_diff
    return round_to_precision(position_size, 6)


def is_profitable_spread(
    funding_rate_1: float,
    funding_rate_2: float,
    min_threshold: float,
    max_threshold: float
) -> Tuple[bool, float, str]:
    """Check if funding rate spread is profitable
    
    Args:
        funding_rate_1: Funding rate from exchange 1
        funding_rate_2: Funding rate from exchange 2
        min_threshold: Minimum profitable threshold
        max_threshold: Maximum safe threshold
        
    Returns:
        Tuple of (is_profitable, spread, direction)
    """
    spread = abs(funding_rate_1 - funding_rate_2)
    
    # Determine direction
    if funding_rate_1 > funding_rate_2:
        direction = "short_ex1_long_ex2"
    else:
        direction = "long_ex1_short_ex2"
    
    # Check profitability
    is_profitable = min_threshold <= spread <= max_threshold
    
    return is_profitable, spread, direction