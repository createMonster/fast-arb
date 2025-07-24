"""Reya Network exchange client"""

import json
import asyncio
import websockets
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from web3 import Web3
from eth_account import Account
from loguru import logger

from .base_exchange import (
    BaseExchange, MarketData, Position, Order, Balance,
    OrderSide, OrderType, OrderStatus
)
from ..utils.helpers import safe_float, get_current_timestamp


class ReyaClient(BaseExchange):
    """Reya Network exchange client
    
    Based on the Reya Python SDK examples:
    https://github.com/Reya-Labs/reya-python-sdk
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("Reya", config)
        
        self.websocket_url = config.get('websocket_url', 'wss://ws.reya.network')
        self.rpc_url = config.get('rpc_url', 'https://rpc.reya.network')
        self.chain_id = config.get('chain_id', 1729)
        self.private_key = config.get('private_key', '')
        self.account_id = config.get('account_id', '')
        
        # Initialize Web3 connection
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        
        # Initialize account if private key is provided and valid
        self.account = None
        if self.private_key and self._is_valid_private_key(self.private_key):
            try:
                self.account = Account.from_key(self.private_key)
            except Exception as e:
                logger.warning(f"Invalid private key provided: {e}")
                self.account = None
        
        # WebSocket connection
        self.ws = None
        self.subscriptions = set()
        self.market_data_cache = {}
        
        # Market data update handlers
        self._funding_rate_handlers = []
        self._price_handlers = []
    
    def _is_valid_private_key(self, private_key: str) -> bool:
        """Check if private key is valid hexadecimal"""
        if not private_key or private_key in ['your_reya_private_key_here', 'test_key', '']:
            return False
        
        try:
            # Remove 0x prefix if present
            key = private_key.replace('0x', '')
            # Check if it's valid hex and correct length (64 characters)
            int(key, 16)
            return len(key) == 64
        except ValueError:
            return False
        
    async def connect(self) -> bool:
        """Connect to Reya Network"""
        try:
            # Test RPC connection
            if not self.w3.is_connected():
                logger.error("Failed to connect to Reya RPC")
                return False
            
            # Connect to WebSocket
            await self._connect_websocket()
            
            self._connected = True
            logger.info(f"Connected to Reya Network (Chain ID: {self.chain_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Reya: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from Reya Network"""
        if self.ws:
            await self.ws.close()
            self.ws = None
        
        self.subscriptions.clear()
        self._connected = False
        logger.info("Disconnected from Reya Network")
    
    async def _connect_websocket(self) -> None:
        """Connect to Reya WebSocket"""
        try:
            self.ws = await websockets.connect(self.websocket_url)
            logger.info(f"Connected to Reya WebSocket: {self.websocket_url}")
            
            # Start message handler
            asyncio.create_task(self._handle_websocket_messages())
            
        except Exception as e:
            logger.error(f"Failed to connect to Reya WebSocket: {e}")
            raise
    
    async def _handle_websocket_messages(self) -> None:
        """Handle incoming WebSocket messages"""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    await self._process_websocket_message(data)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse WebSocket message: {e}")
                except Exception as e:
                    logger.error(f"Error processing WebSocket message: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Reya WebSocket connection closed")
        except Exception as e:
            logger.error(f"WebSocket handler error: {e}")
    
    async def _process_websocket_message(self, data: Dict[str, Any]) -> None:
        """Process WebSocket message"""
        message_type = data.get('type')
        
        if message_type == 'funding_rate':
            await self._handle_funding_rate_update(data)
        elif message_type == 'price':
            await self._handle_price_update(data)
        elif message_type == 'candle':
            await self._handle_candle_update(data)
        else:
            logger.debug(f"Unhandled message type: {message_type}")
    
    async def _handle_funding_rate_update(self, data: Dict[str, Any]) -> None:
        """Handle funding rate update"""
        symbol = data.get('symbol')
        funding_rate = safe_float(data.get('funding_rate'))
        
        if symbol and funding_rate is not None:
            # Update cache
            if symbol not in self.market_data_cache:
                self.market_data_cache[symbol] = {}
            
            self.market_data_cache[symbol]['funding_rate'] = funding_rate
            self.market_data_cache[symbol]['funding_rate_timestamp'] = get_current_timestamp()
            
            logger.debug(f"Funding rate update: {symbol} = {funding_rate}")
    
    async def _handle_price_update(self, data: Dict[str, Any]) -> None:
        """Handle price update"""
        symbol = data.get('symbol')
        price = safe_float(data.get('price'))
        
        if symbol and price is not None:
            # Update cache
            if symbol not in self.market_data_cache:
                self.market_data_cache[symbol] = {}
            
            self.market_data_cache[symbol]['price'] = price
            self.market_data_cache[symbol]['price_timestamp'] = get_current_timestamp()
            
            logger.debug(f"Price update: {symbol} = {price}")
    
    async def _handle_candle_update(self, data: Dict[str, Any]) -> None:
        """Handle candle update"""
        symbol = data.get('symbol')
        candle = data.get('candle', {})
        
        if symbol and candle:
            # Update cache with OHLCV data
            if symbol not in self.market_data_cache:
                self.market_data_cache[symbol] = {}
            
            self.market_data_cache[symbol]['candle'] = candle
            self.market_data_cache[symbol]['candle_timestamp'] = get_current_timestamp()
    
    async def subscribe_to_funding_rates(self, symbols: List[str]) -> None:
        """Subscribe to funding rate updates"""
        if not self.ws:
            raise RuntimeError("WebSocket not connected")
        
        for symbol in symbols:
            normalized_symbol = self.normalize_symbol(symbol)
            subscription = {
                "type": "subscribe",
                "channel": "funding_rate",
                "symbol": normalized_symbol
            }
            
            await self.ws.send(json.dumps(subscription))
            self.subscriptions.add(f"funding_rate:{normalized_symbol}")
            logger.info(f"Subscribed to funding rate: {normalized_symbol}")
    
    async def subscribe_to_prices(self, symbols: List[str]) -> None:
        """Subscribe to price updates"""
        if not self.ws:
            raise RuntimeError("WebSocket not connected")
        
        for symbol in symbols:
            normalized_symbol = self.normalize_symbol(symbol)
            subscription = {
                "type": "subscribe",
                "channel": "price",
                "symbol": normalized_symbol
            }
            
            await self.ws.send(json.dumps(subscription))
            self.subscriptions.add(f"price:{normalized_symbol}")
            logger.info(f"Subscribed to price: {normalized_symbol}")
    
    async def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """Get market data for a symbol"""
        normalized_symbol = self.normalize_symbol(symbol)
        
        if normalized_symbol not in self.market_data_cache:
            return None
        
        cache_data = self.market_data_cache[normalized_symbol]
        
        return MarketData(
            symbol=symbol,
            price=cache_data.get('price', 0.0),
            funding_rate=cache_data.get('funding_rate', 0.0),
            timestamp=datetime.now(timezone.utc),
            volume_24h=None,  # Not available in current cache
            open_interest=None  # Not available in current cache
        )
    
    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        """Get current funding rate for a symbol"""
        normalized_symbol = self.normalize_symbol(symbol)
        
        if normalized_symbol in self.market_data_cache:
            return self.market_data_cache[normalized_symbol].get('funding_rate')
        
        return None
    
    async def get_balance(self) -> List[Balance]:
        """Get account balances"""
        # TODO: Implement using Reya RPC calls
        # This would require implementing the margin account balance queries
        logger.warning("get_balance not yet implemented for Reya")
        return []
    
    async def get_positions(self) -> List[Position]:
        """Get open positions"""
        # TODO: Implement using Reya RPC calls
        # This would require implementing position queries
        logger.warning("get_positions not yet implemented for Reya")
        return []
    
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        amount: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None
    ) -> Optional[Order]:
        """Place an order on Reya"""
        # TODO: Implement using Reya trade execution
        # This would require implementing the trade execution from the SDK
        logger.warning("place_order not yet implemented for Reya")
        return None
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        # TODO: Implement order cancellation
        logger.warning("cancel_order not yet implemented for Reya")
        return False
    
    async def get_order_status(self, order_id: str) -> Optional[Order]:
        """Get order status"""
        # TODO: Implement order status query
        logger.warning("get_order_status not yet implemented for Reya")
        return None
    
    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to Reya format
        
        Args:
            symbol: Standard format (e.g., 'BTC-USD')
            
        Returns:
            Reya format (e.g., 'BTC-rUSD')
        """
        if '-' in symbol:
            base, quote = symbol.split('-')
            if quote.upper() == 'USD':
                quote = 'rUSD'
            return f"{base}-{quote}"
        return symbol
    
    def denormalize_symbol(self, symbol: str) -> str:
        """Convert Reya symbol to standard format
        
        Args:
            symbol: Reya format (e.g., 'BTC-rUSD')
            
        Returns:
            Standard format (e.g., 'BTC-USD')
        """
        if '-' in symbol:
            base, quote = symbol.split('-')
            if quote.upper() == 'RUSD':
                quote = 'USD'
            return f"{base}-{quote}"
        return symbol
    
    async def health_check(self) -> bool:
        """Perform health check"""
        try:
            # Check RPC connection
            if not self.w3.is_connected():
                return False
            
            # Check WebSocket connection
            if not self.ws or self.ws.closed:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Reya health check failed: {e}")
            return False