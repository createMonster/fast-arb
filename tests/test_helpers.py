"""Tests for helper functions"""

import pytest
from datetime import datetime, timezone

from src.utils.helpers import (
    format_currency,
    calculate_percentage_diff,
    calculate_funding_rate_spread,
    validate_trading_pair,
    parse_trading_pair,
    normalize_exchange_symbol,
    safe_float,
    safe_divide,
    round_to_precision,
    calculate_position_size,
    is_funding_rate_spread_profitable
)


class TestHelpers:
    """Test helper functions"""
    
    def test_format_currency(self):
        """Test currency formatting"""
        assert format_currency(1234.56) == "$1,234.56"
        assert format_currency(0.123456, precision=4) == "$0.1235"
        assert format_currency(-1000) == "-$1,000.00"
        assert format_currency(0) == "$0.00"
    
    def test_calculate_percentage_diff(self):
        """Test percentage difference calculation"""
        assert calculate_percentage_diff(100, 110) == 10.0
        assert calculate_percentage_diff(110, 100) == -9.090909090909092
        assert calculate_percentage_diff(0, 100) == float('inf')
        assert calculate_percentage_diff(100, 0) == -100.0
        assert calculate_percentage_diff(0, 0) == 0.0
    
    def test_calculate_funding_rate_spread(self):
        """Test funding rate spread calculation"""
        # Long Reya, Short Hyperliquid scenario
        spread = calculate_funding_rate_spread(0.01, -0.005)  # 1% vs -0.5%
        assert spread == 1.5  # 1.5% spread
        
        # Short Reya, Long Hyperliquid scenario
        spread = calculate_funding_rate_spread(-0.005, 0.01)  # -0.5% vs 1%
        assert spread == -1.5  # -1.5% spread
        
        # Same rates
        spread = calculate_funding_rate_spread(0.01, 0.01)
        assert spread == 0.0
    
    def test_validate_trading_pair(self):
        """Test trading pair validation"""
        assert validate_trading_pair("BTC-USD") is True
        assert validate_trading_pair("ETH-USDT") is True
        assert validate_trading_pair("SOL-USD") is True
        
        assert validate_trading_pair("BTCUSD") is False
        assert validate_trading_pair("BTC/USD") is False
        assert validate_trading_pair("BTC") is False
        assert validate_trading_pair("") is False
        assert validate_trading_pair("BTC-") is False
    
    def test_parse_trading_pair(self):
        """Test trading pair parsing"""
        base, quote = parse_trading_pair("BTC-USD")
        assert base == "BTC"
        assert quote == "USD"
        
        base, quote = parse_trading_pair("ETH-USDT")
        assert base == "ETH"
        assert quote == "USDT"
        
        with pytest.raises(ValueError):
            parse_trading_pair("INVALID")
    
    def test_normalize_exchange_symbol(self):
        """Test exchange symbol normalization"""
        # Test different formats
        assert normalize_exchange_symbol("BTC/USD", "standard") == "BTC-USD"
        assert normalize_exchange_symbol("BTC-USD", "standard") == "BTC-USD"
        assert normalize_exchange_symbol("BTCUSD", "standard") == "BTC-USD"
        
        # Test exchange-specific formats
        assert normalize_exchange_symbol("BTC-USD", "hyperliquid") == "BTC"
        assert normalize_exchange_symbol("ETH-USD", "hyperliquid") == "ETH"
    
    def test_safe_float(self):
        """Test safe float conversion"""
        assert safe_float("123.45") == 123.45
        assert safe_float(123.45) == 123.45
        assert safe_float("invalid", 0.0) == 0.0
        assert safe_float(None, -1.0) == -1.0
        assert safe_float("", 10.0) == 10.0
    
    def test_safe_divide(self):
        """Test safe division"""
        assert safe_divide(10, 2) == 5.0
        assert safe_divide(10, 0) == 0.0
        assert safe_divide(10, 0, 999.0) == 999.0
        assert safe_divide(0, 0) == 0.0
    
    def test_round_to_precision(self):
        """Test precision rounding"""
        assert round_to_precision(123.456789, 2) == 123.46
        assert round_to_precision(123.456789, 4) == 123.4568
        assert round_to_precision(123.456789, 0) == 123.0
        assert round_to_precision(0.000123, 6) == 0.000123
    
    def test_calculate_position_size(self):
        """Test position size calculation"""
        # Test with basic parameters
        size = calculate_position_size(
            available_balance=10000,
            max_position_percentage=0.1,  # 10%
            price=50000,
            leverage=1
        )
        assert size == 0.02  # $1000 / $50000 = 0.02 BTC
        
        # Test with leverage
        size = calculate_position_size(
            available_balance=10000,
            max_position_percentage=0.1,
            price=50000,
            leverage=10
        )
        assert size == 0.2  # With 10x leverage
        
        # Test with minimum size constraint
        size = calculate_position_size(
            available_balance=100,
            max_position_percentage=0.1,
            price=50000,
            leverage=1,
            min_size=0.001
        )
        assert size == 0.001  # Should use minimum size
    
    def test_is_funding_rate_spread_profitable(self):
        """Test funding rate spread profitability check"""
        # Profitable spread
        assert is_funding_rate_spread_profitable(
            spread_percentage=0.5,  # 0.5%
            min_threshold=0.1,      # 0.1%
            trading_fees=0.1,       # 0.1%
            funding_period_hours=8
        ) is True
        
        # Unprofitable spread (below threshold)
        assert is_funding_rate_spread_profitable(
            spread_percentage=0.05,  # 0.05%
            min_threshold=0.1,       # 0.1%
            trading_fees=0.1,
            funding_period_hours=8
        ) is False
        
        # Unprofitable spread (fees too high)
        assert is_funding_rate_spread_profitable(
            spread_percentage=0.2,   # 0.2%
            min_threshold=0.1,       # 0.1%
            trading_fees=0.3,        # 0.3% (higher than spread)
            funding_period_hours=8
        ) is False
        
        # Edge case: exactly at threshold
        assert is_funding_rate_spread_profitable(
            spread_percentage=0.2,   # 0.2%
            min_threshold=0.1,       # 0.1%
            trading_fees=0.1,        # 0.1%
            funding_period_hours=8
        ) is True  # 0.2% - 0.1% = 0.1% profit


class TestTimestampHelpers:
    """Test timestamp-related helpers"""
    
    def test_get_current_timestamp(self):
        """Test current timestamp function"""
        from src.utils.helpers import get_current_timestamp
        
        timestamp = get_current_timestamp()
        assert isinstance(timestamp, float)
        assert timestamp > 0
        
        # Should be close to current time
        current_time = datetime.now(timezone.utc).timestamp()
        assert abs(timestamp - current_time) < 1  # Within 1 second
    
    def test_timestamp_to_datetime(self):
        """Test timestamp to datetime conversion"""
        from src.utils.helpers import timestamp_to_datetime
        
        timestamp = 1640995200.0  # 2022-01-01 00:00:00 UTC
        dt = timestamp_to_datetime(timestamp)
        
        assert isinstance(dt, datetime)
        assert dt.year == 2022
        assert dt.month == 1
        assert dt.day == 1
        assert dt.hour == 0
        assert dt.minute == 0
        assert dt.second == 0
        assert dt.tzinfo == timezone.utc
    
    def test_datetime_to_timestamp(self):
        """Test datetime to timestamp conversion"""
        from src.utils.helpers import datetime_to_timestamp
        
        dt = datetime(2022, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        timestamp = datetime_to_timestamp(dt)
        
        assert isinstance(timestamp, float)
        assert timestamp == 1640995200.0