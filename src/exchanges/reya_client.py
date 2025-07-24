"""Reya Network exchange client using official SDK"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from loguru import logger

# Import from official Reya SDK
try:
    from reya_data_feed.consumer import ReyaSocket
    from reya_actions.actions.trade import trade, TradeParams
    from reya_actions.actions.create_account import create_account
    from reya_actions.config import get_config
    from reya_actions.types import MarketIds
except ImportError as e:
    logger.error(f"Failed to import Reya SDK: {e}")
    logger.error("Please install the Reya SDK dependencies")
    raise

from .base_exchange import (
    BaseExchange, MarketData, Position, Order, Balance,
    OrderSide, OrderType, OrderStatus
)
from ..utils.helpers import safe_float, get_current_timestamp


class ReyaClient(BaseExchange):
    """Reya Network exchange client using official SDK
    
    Integrates with the official Reya Python SDK:
    https://github.com/Reya-Labs/reya-python-sdk
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("Reya", config)
        
        # Configuration from official SDK requirements
        self.websocket_url = config.get('websocket_url', 'wss://ws.reya.network')
        self.rpc_url = config.get('rpc_url', 'https://rpc.reya.network')
        self.chain_id = config.get('chain_id', 1729)
        self.private_key = config.get('private_key', '')
        self.account_id = config.get('account_id', '')
        
        # Validate required configuration
        if not self.private_key:
            logger.warning("No private key provided for Reya client")
        if not self.account_id:
            logger.warning("No account ID provided for Reya client")
        
        # Initialize SDK components
        self.ws_consumer: Optional[ReyaSocket] = None
        self.sdk_config: Optional[dict] = None
        self.market_data_cache = {}
        self.subscriptions = set()
        
        # Market data update handlers
        self._funding_rate_handlers = []
        self._price_handlers = []
    
    async def connect(self) -> bool:
        """Connect to Reya Network using official SDK"""
        try:
            # Get SDK configuration
            self.sdk_config = get_config()
            
            # Initialize WebSocket consumer from SDK
            self.ws_consumer = ReyaSocket()
            
            # Connect to WebSocket
            await self.ws_consumer.connect()
            
            # Setup message handlers
            self.ws_consumer.on_funding_rate_update = self._handle_funding_rate_update
            self.ws_consumer.on_price_update = self._handle_price_update
            self.ws_consumer.on_candle_update = self._handle_candle_update
            
            self._connected = True
            logger.info(f"Connected to Reya Network using official SDK (Chain ID: {self.chain_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Reya using SDK: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from Reya Network"""
        if self.ws_consumer:
            await self.ws_consumer.disconnect()
            self.ws_consumer = None
        
        self.subscriptions.clear()
        self._connected = False
        logger.info("Disconnected from Reya Network")
    
    async def _handle_funding_rate_update(self, data: Dict[str, Any]) -> None:
        """Handle funding rate update from SDK <mcreference link="https://github.com/Reya-Labs/reya-python-sdk" index="1">1</mcreference>"""
        symbol = data.get('symbol')
        funding_rate = safe_float(data.get('funding_rate'))
        
        if symbol and funding_rate is not None:
            # Update cache
            if symbol not in self.market_data_cache:
                self.market_data_cache[symbol] = {}
            
            self.market_data_cache[symbol]['funding_rate'] = funding_rate
            self.market_data_cache[symbol]['funding_rate_timestamp'] = get_current_timestamp()
            
            logger.debug(f"Funding rate update: {symbol} = {funding_rate}")
            
            # Notify handlers
            for handler in self._funding_rate_handlers:
                try:
                    await handler(symbol, funding_rate)
                except Exception as e:
                    logger.error(f"Error in funding rate handler: {e}")
    
    async def _handle_price_update(self, data: Dict[str, Any]) -> None:
        """Handle price update from SDK <mcreference link="https://github.com/Reya-Labs/reya-python-sdk" index="1">1</mcreference>"""
        symbol = data.get('symbol')
        price = safe_float(data.get('price'))
        
        if symbol and price is not None:
            # Update cache
            if symbol not in self.market_data_cache:
                self.market_data_cache[symbol] = {}
            
            self.market_data_cache[symbol]['price'] = price
            self.market_data_cache[symbol]['price_timestamp'] = get_current_timestamp()
            
            logger.debug(f"Price update: {symbol} = {price}")
            
            # Notify handlers
            for handler in self._price_handlers:
                try:
                    await handler(symbol, price)
                except Exception as e:
                    logger.error(f"Error in price handler: {e}")
    
    async def _handle_candle_update(self, data: Dict[str, Any]) -> None:
        """Handle candle update from SDK <mcreference link="https://github.com/Reya-Labs/reya-python-sdk" index="1">1</mcreference>"""
        symbol = data.get('symbol')
        candle = data.get('candle', {})
        
        if symbol and candle:
            # Update cache with OHLCV data
            if symbol not in self.market_data_cache:
                self.market_data_cache[symbol] = {}
            
            self.market_data_cache[symbol]['candle'] = candle
            self.market_data_cache[symbol]['candle_timestamp'] = get_current_timestamp()
    
    async def subscribe_to_funding_rates(self, symbols: List[str]) -> None:
        """Subscribe to funding rate updates using SDK <mcreference link="https://github.com/Reya-Labs/reya-python-sdk" index="1">1</mcreference>"""
        if not self.ws_consumer:
            raise RuntimeError("WebSocket consumer not initialized")
        
        for symbol in symbols:
            normalized_symbol = self.normalize_symbol(symbol)
            await self.ws_consumer.subscribe_to_funding_rates([normalized_symbol])
            self.subscriptions.add(f"funding_rate:{normalized_symbol}")
            logger.info(f"Subscribed to funding rate: {normalized_symbol}")
    
    async def subscribe_to_prices(self, symbols: List[str]) -> None:
        """Subscribe to price updates using SDK <mcreference link="https://github.com/Reya-Labs/reya-python-sdk" index="1">1</mcreference>"""
        if not self.ws_consumer:
            raise RuntimeError("WebSocket consumer not initialized")
        
        for symbol in symbols:
            normalized_symbol = self.normalize_symbol(symbol)
            await self.ws_consumer.subscribe_to_prices([normalized_symbol])
            self.subscriptions.add(f"price:{normalized_symbol}")
            logger.info(f"Subscribed to prices: {normalized_symbol}")
    
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
            volume_24h=0.0,  # TODO: Add volume data when available from SDK
            open_interest=0.0  # TODO: Add OI data when available from SDK
        )
    
    async def get_balance(self) -> Optional[Balance]:
        """Get account balance using SDK contract calls"""
        if not self.account_id or not self.sdk_config:
            logger.warning("No account ID or SDK config available for balance query")
            return None
        
        try:
            # Get core contract from SDK config
            core_contract = self.sdk_config["w3contracts"]["core"]
            
            # Call getUsdNodeMarginInfo to get balance information
            margin_info = core_contract.functions.getUsdNodeMarginInfo(
                int(self.account_id)
            ).call()
            
            # Extract balance data (amounts are in wei, convert to readable format)
            margin_balance = margin_info[1] / 10**6  # marginBalance scaled by 10^6
            real_balance = margin_info[2] / 10**6    # realBalance scaled by 10^6
            
            return Balance(
                total=safe_float(real_balance),
                available=safe_float(margin_balance),
                used=safe_float(max(0, real_balance - margin_balance)),
                currency='rUSD'  # Reya's native currency
            )
            
        except Exception as e:
            logger.error(f"Failed to get balance from Reya SDK: {e}")
            return None
    
    async def get_positions(self) -> List[Position]:
        """Get open positions using SDK contract calls"""
        if not self.account_id or not self.sdk_config:
            logger.warning("No account ID or SDK config available for positions query")
            return []
        
        try:
            # Get passive perp contract from SDK config
            passive_perp_contract = self.sdk_config["w3contracts"]["passive_perp"]
            
            positions = []
            
            # Query positions for each market (ETH, BTC, SOL, etc.)
            for market_id in [MarketIds.ETH.value, MarketIds.BTC.value, MarketIds.SOL.value, MarketIds.ARB.value, MarketIds.OP.value]:
                try:
                    # Call getUpdatedPositionInfo to get position data
                    position_info = passive_perp_contract.functions.getUpdatedPositionInfo(
                        market_id, int(self.account_id)
                    ).call()
                    
                    # Extract position data
                    base_amount = position_info[0] / 10**18  # base amount scaled by 10^18
                    realized_pnl = position_info[1] / 10**18  # realized PnL scaled by 10^18
                    last_price = position_info[2][0] / 10**18  # last price scaled by 10^18
                    
                    # Only include positions with non-zero base amount
                    if abs(base_amount) > 0.001:  # Minimum position size threshold
                        # Map market ID to symbol
                        symbol_map = {
                            MarketIds.ETH.value: "ETH-rUSD",
                            MarketIds.BTC.value: "BTC-rUSD", 
                            MarketIds.SOL.value: "SOL-rUSD",
                            MarketIds.ARB.value: "ARB-rUSD",
                            MarketIds.OP.value: "OP-rUSD"
                        }
                        
                        position = Position(
                            symbol=symbol_map.get(market_id, f"MARKET_{market_id}"),
                            side=OrderSide.LONG if base_amount > 0 else OrderSide.SHORT,
                            size=abs(base_amount),
                            entry_price=0.0,  # Entry price not directly available
                            mark_price=last_price,
                            unrealized_pnl=0.0,  # Would need additional calculation
                            timestamp=datetime.now(timezone.utc)
                        )
                        positions.append(position)
                        
                except Exception as market_error:
                    logger.debug(f"No position found for market {market_id}: {market_error}")
                    continue
            
            return positions
            
        except Exception as e:
            logger.error(f"Failed to get positions from Reya SDK: {e}")
            return []
    
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        amount: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None
    ) -> Optional[Order]:
        """Place an order using SDK trade execution"""
        if not self.sdk_config or not self.account_id:
            logger.error("SDK config and account ID required for trading")
            return None
        
        try:
            # Convert to SDK format
            # Negative amount for short, positive for long
            base_amount = amount if side == OrderSide.LONG else -amount
            
            # Convert to 18 decimal precision as required by SDK
            base_amount_wei = int(base_amount * 10**18)
            
            # Set price limit (required by SDK)
            if price is None:
                # Get current market price for limit calculation
                market_data = await self.get_market_data(symbol)
                if not market_data:
                    logger.error(f"No market data available for {symbol}")
                    return None
                
                # Add slippage tolerance (1% for market orders)
                slippage = 0.01
                if side == OrderSide.LONG:
                    price_limit = market_data.price * (1 + slippage)
                else:
                    price_limit = market_data.price * (1 - slippage)
            else:
                price_limit = price
            
            # Convert price to 18 decimal precision
            price_limit_wei = int(price_limit * 10**18)
            
            # Map symbol to market ID
            symbol_to_market = {
                "ETH-rUSD": MarketIds.ETH.value,
                "BTC-rUSD": MarketIds.BTC.value,
                "SOL-rUSD": MarketIds.SOL.value,
                "ARB-rUSD": MarketIds.ARB.value,
                "OP-rUSD": MarketIds.OP.value
            }
            
            normalized_symbol = self.normalize_symbol(symbol)
            market_id = symbol_to_market.get(normalized_symbol)
            if not market_id:
                logger.error(f"Unknown market symbol: {normalized_symbol}")
                return None
            
            # Create trade parameters
            trade_params = TradeParams(
                account_id=int(self.account_id),
                market_id=market_id,
                base=base_amount_wei,
                price_limit=price_limit_wei
            )
            
            # Execute trade using SDK
            result = trade(self.sdk_config, trade_params)
            
            if result and result.get('tx_receipt'):
                order = Order(
                    id=result['tx_receipt'].transactionHash.hex(),
                    symbol=symbol,
                    side=side,
                    amount=amount,
                    price=price_limit,
                    order_type=order_type,
                    status=OrderStatus.FILLED,  # Assume filled for successful execution
                    timestamp=datetime.now(timezone.utc)
                )
                
                logger.info(f"Order executed successfully: {order.id}")
                return order
            else:
                logger.error(f"Trade execution failed: {result}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to place order using Reya SDK: {e}")
            return None
    
    async def get_order_status(self, order_id: str) -> Optional[Order]:
        """Get order status"""
        # TODO: Implement order status query when available in SDK
        logger.warning("get_order_status not yet implemented in Reya SDK")
        return None
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        # TODO: Implement order cancellation when available in SDK
        logger.warning("cancel_order not yet implemented in Reya SDK")
        return False
    
    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol format for Reya"""
        # Reya uses format like 'SOL-rUSD'
        if '-' not in symbol:
            return f"{symbol}-rUSD"
        return symbol
    
    async def health_check(self) -> bool:
        """Perform health check"""
        try:
            # Check WebSocket connection
            if not self.ws_consumer or not self._connected:
                return False
            
            # Check if we can get balance (tests RPC connectivity)
            balance = await self.get_balance()
            return balance is not None
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    def add_funding_rate_handler(self, handler) -> None:
        """Add funding rate update handler"""
        self._funding_rate_handlers.append(handler)
    
    def add_price_handler(self, handler) -> None:
        """Add price update handler"""
        self._price_handlers.append(handler)