"""Hyperliquid exchange client using CCXT"""

import ccxt
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from loguru import logger

from .base_exchange import (
    BaseExchange, MarketData, Position, Order, Balance,
    OrderSide, OrderType, OrderStatus
)
from ..utils.helpers import safe_float


class HyperliquidClient(BaseExchange):
    """Hyperliquid exchange client using CCXT"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("Hyperliquid", config)
        
        self.api_url = config.get('api_url', 'https://api.hyperliquid.xyz')
        self.private_key = config.get('private_key', '')
        
        # Validate private key
        if not self._is_valid_private_key(self.private_key):
            logger.warning("Invalid or missing Hyperliquid private key. Some features may not work.")
            self.private_key = ''
        
        # Initialize CCXT exchange
        self.exchange = None
        self._init_exchange()
    
    def _is_valid_private_key(self, private_key: str) -> bool:
        """Check if private key is valid hexadecimal"""
        if not private_key or private_key in ['your_hyperliquid_private_key_here', 'test_key', '']:
            return False
        
        try:
            # Remove 0x prefix if present
            key = private_key.replace('0x', '')
            # Check if it's valid hex and correct length (64 characters)
            int(key, 16)
            return len(key) == 64
        except ValueError:
            return False
        
    def _init_exchange(self) -> None:
        """Initialize CCXT exchange instance"""
        try:
            # Note: Hyperliquid might not be directly supported by CCXT
            # This is a placeholder implementation
            # In practice, you might need to use Hyperliquid's native API
            
            self.exchange = ccxt.hyperliquid({
                'apiKey': '',  # Hyperliquid uses different auth
                'secret': '',
                'password': '',
                'sandbox': False,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',  # For perpetual futures
                }
            })
            
            # Set private key if provided
            if self.private_key:
                # Hyperliquid uses wallet-based authentication
                self.exchange.apiKey = self.private_key
                
        except Exception as e:
            logger.warning(f"CCXT Hyperliquid not available, using custom implementation: {e}")
            self.exchange = None
    
    async def connect(self) -> bool:
        """Connect to Hyperliquid"""
        try:
            if self.exchange:
                # Test connection with CCXT
                await self._test_ccxt_connection()
            else:
                # Use custom API implementation
                await self._test_custom_connection()
            
            self._connected = True
            logger.info("Connected to Hyperliquid")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Hyperliquid: {e}")
            return False
    
    async def _test_ccxt_connection(self) -> None:
        """Test CCXT connection"""
        if self.exchange:
            # Test by fetching markets
            markets = await self.exchange.load_markets()
            if not markets:
                raise RuntimeError("No markets available")
    
    async def _test_custom_connection(self) -> None:
        """Test custom API connection"""
        # Implement custom Hyperliquid API test
        # This would involve making a simple API call to verify connectivity
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_url}/info") as response:
                if response.status != 200:
                    raise RuntimeError(f"API test failed: {response.status}")
    
    async def disconnect(self) -> None:
        """Disconnect from Hyperliquid"""
        if self.exchange and hasattr(self.exchange, 'close'):
            try:
                await self.exchange.close()
            except Exception as e:
                logger.debug(f"Error closing exchange connection: {e}")
        
        self._connected = False
        logger.info("Disconnected from Hyperliquid")
    
    async def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """Get market data for a symbol"""
        try:
            normalized_symbol = self.normalize_symbol(symbol)
            
            if self.exchange:
                # Use CCXT
                ticker = await self.exchange.fetch_ticker(normalized_symbol)
                funding_rate = await self._get_funding_rate_ccxt(normalized_symbol)
                
                return MarketData(
                    symbol=symbol,
                    price=safe_float(ticker.get('last', 0)),
                    funding_rate=funding_rate or 0.0,
                    timestamp=datetime.now(timezone.utc),
                    volume_24h=safe_float(ticker.get('quoteVolume')),
                    open_interest=None  # Would need separate API call
                )
            else:
                # Use custom API
                return await self._get_market_data_custom(normalized_symbol, symbol)
                
        except Exception as e:
            logger.error(f"Failed to get market data for {symbol}: {e}")
            return None
    
    async def _get_funding_rate_ccxt(self, symbol: str) -> Optional[float]:
        """Get funding rate using CCXT"""
        try:
            if hasattr(self.exchange, 'fetch_funding_rate'):
                funding_data = await self.exchange.fetch_funding_rate(symbol)
                return safe_float(funding_data.get('fundingRate'))
        except Exception as e:
            logger.debug(f"CCXT funding rate fetch failed: {e}")
        return None
    
    async def _get_market_data_custom(self, normalized_symbol: str, original_symbol: str) -> Optional[MarketData]:
        """Get market data using custom API"""
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                # Get price data
                async with session.get(f"{self.api_url}/info") as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Parse Hyperliquid response
                        # This is a placeholder - actual implementation depends on API structure
                        universe = data.get('universe', [])
                        
                        for market in universe:
                            if market.get('name') == normalized_symbol:
                                # Get current price and funding rate
                                price = safe_float(market.get('markPx', 0))
                                funding_rate = safe_float(market.get('funding', 0))
                                
                                return MarketData(
                                    symbol=original_symbol,
                                    price=price,
                                    funding_rate=funding_rate,
                                    timestamp=datetime.now(timezone.utc),
                                    volume_24h=None,
                                    open_interest=None
                                )
        except Exception as e:
            logger.error(f"Custom API call failed: {e}")
        
        return None
    
    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        """Get current funding rate for a symbol"""
        market_data = await self.get_market_data(symbol)
        return market_data.funding_rate if market_data else None
    
    async def get_balance(self) -> List[Balance]:
        """Get account balances"""
        try:
            if self.exchange:
                balance_data = await self.exchange.fetch_balance()
                balances = []
                
                for currency, balance in balance_data.items():
                    if isinstance(balance, dict) and 'total' in balance:
                        balances.append(Balance(
                            currency=currency,
                            total=safe_float(balance.get('total', 0)),
                            available=safe_float(balance.get('free', 0)),
                            locked=safe_float(balance.get('used', 0))
                        ))
                
                return balances
            else:
                # Custom API implementation
                return await self._get_balance_custom()
                
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return []
    
    async def _get_balance_custom(self) -> List[Balance]:
        """Get balance using custom API"""
        # TODO: Implement custom balance API call
        logger.warning("Custom balance API not implemented")
        return []
    
    async def get_positions(self) -> List[Position]:
        """Get open positions"""
        try:
            if self.exchange:
                positions_data = await self.exchange.fetch_positions()
                positions = []
                
                for pos_data in positions_data:
                    if safe_float(pos_data.get('contracts', 0)) != 0:
                        side = OrderSide.BUY if pos_data.get('side') == 'long' else OrderSide.SELL
                        
                        positions.append(Position(
                            symbol=self.denormalize_symbol(pos_data.get('symbol', '')),
                            side=side,
                            size=safe_float(pos_data.get('contracts', 0)),
                            entry_price=safe_float(pos_data.get('entryPrice', 0)),
                            mark_price=safe_float(pos_data.get('markPrice', 0)),
                            unrealized_pnl=safe_float(pos_data.get('unrealizedPnl', 0)),
                            timestamp=datetime.now(timezone.utc)
                        ))
                
                return positions
            else:
                return await self._get_positions_custom()
                
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
    
    async def _get_positions_custom(self) -> List[Position]:
        """Get positions using custom API"""
        # TODO: Implement custom positions API call
        logger.warning("Custom positions API not implemented")
        return []
    
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        amount: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None
    ) -> Optional[Order]:
        """Place an order"""
        try:
            normalized_symbol = self.normalize_symbol(symbol)
            
            if self.exchange:
                # Use CCXT
                order_data = await self.exchange.create_order(
                    symbol=normalized_symbol,
                    type=order_type.value,
                    side=side.value,
                    amount=amount,
                    price=price
                )
                
                return Order(
                    id=str(order_data.get('id', '')),
                    symbol=symbol,
                    side=side,
                    type=order_type,
                    amount=amount,
                    price=price,
                    status=OrderStatus.PENDING,
                    filled_amount=safe_float(order_data.get('filled', 0)),
                    timestamp=datetime.now(timezone.utc)
                )
            else:
                # Custom API implementation
                return await self._place_order_custom(symbol, side, amount, order_type, price)
                
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return None
    
    async def _place_order_custom(self, symbol: str, side: OrderSide, amount: float, order_type: OrderType, price: Optional[float]) -> Optional[Order]:
        """Place order using custom API"""
        # TODO: Implement custom order placement
        logger.warning("Custom order placement not implemented")
        return None
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        try:
            if self.exchange:
                await self.exchange.cancel_order(order_id)
                return True
            else:
                return await self._cancel_order_custom(order_id)
                
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    async def _cancel_order_custom(self, order_id: str) -> bool:
        """Cancel order using custom API"""
        # TODO: Implement custom order cancellation
        logger.warning("Custom order cancellation not implemented")
        return False
    
    async def get_order_status(self, order_id: str) -> Optional[Order]:
        """Get order status"""
        try:
            if self.exchange:
                order_data = await self.exchange.fetch_order(order_id)
                
                return Order(
                    id=str(order_data.get('id', '')),
                    symbol=self.denormalize_symbol(order_data.get('symbol', '')),
                    side=OrderSide.BUY if order_data.get('side') == 'buy' else OrderSide.SELL,
                    type=OrderType.MARKET if order_data.get('type') == 'market' else OrderType.LIMIT,
                    amount=safe_float(order_data.get('amount', 0)),
                    price=safe_float(order_data.get('price')),
                    status=self._parse_order_status(order_data.get('status', '')),
                    filled_amount=safe_float(order_data.get('filled', 0)),
                    timestamp=datetime.fromtimestamp(order_data.get('timestamp', 0) / 1000, timezone.utc)
                )
            else:
                return await self._get_order_status_custom(order_id)
                
        except Exception as e:
            logger.error(f"Failed to get order status for {order_id}: {e}")
            return None
    
    async def _get_order_status_custom(self, order_id: str) -> Optional[Order]:
        """Get order status using custom API"""
        # TODO: Implement custom order status query
        logger.warning("Custom order status query not implemented")
        return None
    
    def _parse_order_status(self, status: str) -> OrderStatus:
        """Parse order status from exchange format"""
        status_map = {
            'open': OrderStatus.OPEN,
            'closed': OrderStatus.FILLED,
            'canceled': OrderStatus.CANCELLED,
            'cancelled': OrderStatus.CANCELLED,
            'rejected': OrderStatus.REJECTED
        }
        return status_map.get(status.lower(), OrderStatus.PENDING)
    
    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to Hyperliquid format
        
        Args:
            symbol: Standard format (e.g., 'BTC-USD')
            
        Returns:
            Hyperliquid format (e.g., 'BTC')
        """
        if '-' in symbol:
            base, _ = symbol.split('-')
            return base.upper()
        return symbol.upper()
    
    def denormalize_symbol(self, symbol: str) -> str:
        """Convert Hyperliquid symbol to standard format
        
        Args:
            symbol: Hyperliquid format (e.g., 'BTC')
            
        Returns:
            Standard format (e.g., 'BTC-USD')
        """
        # Hyperliquid typically uses USD as quote currency for perpetuals
        if '-' not in symbol:
            return f"{symbol.upper()}-USD"
        return symbol
    
    async def health_check(self) -> bool:
        """Perform health check"""
        try:
            if self.exchange:
                # Test with CCXT
                await self.exchange.fetch_status()
                return True
            else:
                # Test with custom API
                await self._test_custom_connection()
                return True
                
        except Exception as e:
            logger.error(f"Hyperliquid health check failed: {e}")
            return False