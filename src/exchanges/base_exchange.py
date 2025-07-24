"""Base exchange class defining common interface"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderSide(Enum):
    """Order side enumeration"""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type enumeration"""
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(Enum):
    """Order status enumeration"""
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class MarketData:
    """Market data structure"""
    symbol: str
    price: float
    funding_rate: float
    timestamp: datetime
    volume_24h: Optional[float] = None
    open_interest: Optional[float] = None


@dataclass
class Position:
    """Position data structure"""
    symbol: str
    side: OrderSide
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    timestamp: datetime


@dataclass
class Order:
    """Order data structure"""
    id: str
    symbol: str
    side: OrderSide
    type: OrderType
    amount: float
    price: Optional[float]
    status: OrderStatus
    filled_amount: float
    timestamp: datetime


@dataclass
class Balance:
    """Account balance structure"""
    currency: str
    total: float
    available: float
    locked: float


class BaseExchange(ABC):
    """Base class for all exchange implementations"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self._connected = False
        
    @property
    def is_connected(self) -> bool:
        """Check if exchange is connected"""
        return self._connected
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the exchange
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the exchange"""
        pass
    
    @abstractmethod
    async def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """Get market data for a symbol
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Market data or None if not available
        """
        pass
    
    @abstractmethod
    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        """Get current funding rate for a symbol
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Funding rate or None if not available
        """
        pass
    
    @abstractmethod
    async def get_balance(self) -> List[Balance]:
        """Get account balances
        
        Returns:
            List of account balances
        """
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """Get open positions
        
        Returns:
            List of open positions
        """
        pass
    
    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        amount: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None
    ) -> Optional[Order]:
        """Place an order
        
        Args:
            symbol: Trading pair symbol
            side: Order side (buy/sell)
            amount: Order amount
            order_type: Order type (market/limit)
            price: Order price (required for limit orders)
            
        Returns:
            Order object or None if failed
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancellation successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str) -> Optional[Order]:
        """Get order status
        
        Args:
            order_id: Order ID
            
        Returns:
            Order object or None if not found
        """
        pass
    
    @abstractmethod
    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to exchange format
        
        Args:
            symbol: Standard symbol format (e.g., 'BTC-USD')
            
        Returns:
            Exchange-specific symbol format
        """
        pass
    
    @abstractmethod
    def denormalize_symbol(self, symbol: str) -> str:
        """Convert exchange symbol to standard format
        
        Args:
            symbol: Exchange-specific symbol
            
        Returns:
            Standard symbol format (e.g., 'BTC-USD')
        """
        pass
    
    async def health_check(self) -> bool:
        """Perform health check
        
        Returns:
            True if exchange is healthy, False otherwise
        """
        try:
            # Basic connectivity test
            if not self.is_connected:
                return False
            
            # Try to get balance as a health check
            balances = await self.get_balance()
            return balances is not None
            
        except Exception:
            return False
    
    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.name})"
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', connected={self.is_connected})"