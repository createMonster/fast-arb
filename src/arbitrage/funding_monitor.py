"""Funding Rate Monitor for arbitrage opportunities"""

import asyncio
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timezone
from dataclasses import dataclass
from loguru import logger

from ..exchanges.base_exchange import BaseExchange
from ..config.config_manager import TradingPair
from ..utils.helpers import (
    calculate_funding_rate_spread,
    is_profitable_spread,
    get_current_timestamp,
    format_timestamp
)


@dataclass
class FundingRateData:
    """Funding rate data structure"""
    symbol: str
    exchange: str
    funding_rate: float
    timestamp: datetime
    next_funding_time: Optional[datetime] = None


@dataclass
class FundingRateSpread:
    """Funding rate spread data"""
    symbol: str
    reya_rate: float
    hyperliquid_rate: float
    spread: float
    spread_percentage: float
    direction: str  # "long_reya_short_hl" or "short_reya_long_hl"
    timestamp: datetime
    is_profitable: bool


class FundingRateMonitor:
    """Monitor funding rates across exchanges for arbitrage opportunities"""
    
    def __init__(
        self,
        reya_client: BaseExchange,
        hyperliquid_client: BaseExchange,
        trading_pairs: List[TradingPair],
        update_interval: int = 60
    ):
        self.reya_client = reya_client
        self.hyperliquid_client = hyperliquid_client
        self.trading_pairs = trading_pairs
        self.update_interval = update_interval
        
        # Data storage
        self.funding_rates: Dict[str, Dict[str, FundingRateData]] = {}
        self.spreads: Dict[str, FundingRateSpread] = {}
        
        # Event handlers
        self.spread_update_handlers: List[Callable[[FundingRateSpread], None]] = []
        self.opportunity_handlers: List[Callable[[FundingRateSpread], None]] = []
        
        # Control flags
        self._running = False
        self._monitor_task = None
        
        logger.info(f"Initialized FundingRateMonitor for {len(trading_pairs)} pairs")
    
    def add_spread_update_handler(self, handler: Callable[[FundingRateSpread], None]) -> None:
        """Add handler for spread updates"""
        self.spread_update_handlers.append(handler)
    
    def add_opportunity_handler(self, handler: Callable[[FundingRateSpread], None]) -> None:
        """Add handler for arbitrage opportunities"""
        self.opportunity_handlers.append(handler)
    
    async def start_monitoring(self) -> None:
        """Start monitoring funding rates"""
        if self._running:
            logger.warning("Funding rate monitor is already running")
            return
        
        self._running = True
        
        # Subscribe to funding rate updates
        await self._setup_subscriptions()
        
        # Start monitoring task
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info("Started funding rate monitoring")
    
    async def stop_monitoring(self) -> None:
        """Stop monitoring funding rates"""
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped funding rate monitoring")
    
    async def _setup_subscriptions(self) -> None:
        """Setup WebSocket subscriptions for funding rates"""
        try:
            # Get symbols for each exchange
            reya_symbols = [pair.reya_symbol for pair in self.trading_pairs if pair.enabled]
            hyperliquid_symbols = [pair.hyperliquid_symbol for pair in self.trading_pairs if pair.enabled]
            
            # Subscribe to Reya funding rates
            if hasattr(self.reya_client, 'subscribe_to_funding_rates'):
                await self.reya_client.subscribe_to_funding_rates(reya_symbols)
                logger.info(f"Subscribed to Reya funding rates: {reya_symbols}")
            
            # Note: Hyperliquid might not have WebSocket subscriptions
            # We'll poll it in the monitor loop
            
        except Exception as e:
            logger.error(f"Failed to setup subscriptions: {e}")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop"""
        while self._running:
            try:
                await self._update_funding_rates()
                await self._calculate_spreads()
                await asyncio.sleep(self.update_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)  # Short delay before retry
    
    async def _update_funding_rates(self) -> None:
        """Update funding rates from all exchanges"""
        tasks = []
        
        for pair in self.trading_pairs:
            if not pair.enabled:
                continue
            
            # Update Reya funding rate
            tasks.append(self._update_exchange_funding_rate(
                self.reya_client, "reya", pair.symbol, pair.reya_symbol
            ))
            
            # Update Hyperliquid funding rate
            tasks.append(self._update_exchange_funding_rate(
                self.hyperliquid_client, "hyperliquid", pair.symbol, pair.hyperliquid_symbol
            ))
        
        # Execute all updates concurrently
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _update_exchange_funding_rate(
        self,
        exchange: BaseExchange,
        exchange_name: str,
        standard_symbol: str,
        exchange_symbol: str
    ) -> None:
        """Update funding rate for a specific exchange"""
        try:
            funding_rate = await exchange.get_funding_rate(exchange_symbol)
            
            if funding_rate is not None:
                # Initialize symbol data if not exists
                if standard_symbol not in self.funding_rates:
                    self.funding_rates[standard_symbol] = {}
                
                # Store funding rate data
                self.funding_rates[standard_symbol][exchange_name] = FundingRateData(
                    symbol=standard_symbol,
                    exchange=exchange_name,
                    funding_rate=funding_rate,
                    timestamp=datetime.now(timezone.utc)
                )
                
                logger.debug(f"Updated {exchange_name} funding rate for {standard_symbol}: {funding_rate}")
            else:
                logger.warning(f"Failed to get funding rate from {exchange_name} for {exchange_symbol}")
                
        except Exception as e:
            logger.error(f"Error updating funding rate for {exchange_name} {exchange_symbol}: {e}")
    
    async def _calculate_spreads(self) -> None:
        """Calculate funding rate spreads and detect opportunities"""
        for symbol, rates_data in self.funding_rates.items():
            try:
                # Check if we have data from both exchanges
                if "reya" not in rates_data or "hyperliquid" not in rates_data:
                    continue
                
                reya_data = rates_data["reya"]
                hl_data = rates_data["hyperliquid"]
                
                # Calculate spread
                reya_rate = reya_data.funding_rate
                hl_rate = hl_data.funding_rate
                spread = calculate_funding_rate_spread(reya_rate, hl_rate)
                spread_percentage = abs((reya_rate - hl_rate) / max(abs(hl_rate), 0.0001)) * 100
                
                # Determine direction
                if reya_rate > hl_rate:
                    direction = "short_reya_long_hl"
                else:
                    direction = "long_reya_short_hl"
                
                # Find trading pair config
                pair_config = next((p for p in self.trading_pairs if p.symbol == symbol), None)
                if not pair_config:
                    continue
                
                # Check if profitable
                is_profitable, _, _ = is_profitable_spread(
                    reya_rate,
                    hl_rate,
                    pair_config.min_funding_rate_diff,
                    10.0  # Max threshold - could be configurable
                )
                
                # Create spread object
                spread_obj = FundingRateSpread(
                    symbol=symbol,
                    reya_rate=reya_rate,
                    hyperliquid_rate=hl_rate,
                    spread=spread,
                    spread_percentage=spread_percentage,
                    direction=direction,
                    timestamp=datetime.now(timezone.utc),
                    is_profitable=is_profitable
                )
                
                # Store spread
                self.spreads[symbol] = spread_obj
                
                # Notify handlers
                await self._notify_spread_handlers(spread_obj)
                
                if is_profitable:
                    await self._notify_opportunity_handlers(spread_obj)
                    logger.info(
                        f"Arbitrage opportunity detected: {symbol} "
                        f"spread={spread:.4f}% direction={direction}"
                    )
                
            except Exception as e:
                logger.error(f"Error calculating spread for {symbol}: {e}")
    
    async def _notify_spread_handlers(self, spread: FundingRateSpread) -> None:
        """Notify spread update handlers"""
        for handler in self.spread_update_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(spread)
                else:
                    handler(spread)
            except Exception as e:
                logger.error(f"Error in spread update handler: {e}")
    
    async def _notify_opportunity_handlers(self, spread: FundingRateSpread) -> None:
        """Notify opportunity handlers"""
        for handler in self.opportunity_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(spread)
                else:
                    handler(spread)
            except Exception as e:
                logger.error(f"Error in opportunity handler: {e}")
    
    def get_current_spreads(self) -> Dict[str, FundingRateSpread]:
        """Get current funding rate spreads"""
        return self.spreads.copy()
    
    def get_funding_rates(self) -> Dict[str, Dict[str, FundingRateData]]:
        """Get current funding rates"""
        return self.funding_rates.copy()
    
    def get_spread_for_symbol(self, symbol: str) -> Optional[FundingRateSpread]:
        """Get spread for a specific symbol"""
        return self.spreads.get(symbol)
    
    def get_profitable_opportunities(self) -> List[FundingRateSpread]:
        """Get all current profitable opportunities"""
        return [spread for spread in self.spreads.values() if spread.is_profitable]
    
    def is_running(self) -> bool:
        """Check if monitor is running"""
        return self._running
    
    async def force_update(self) -> None:
        """Force an immediate update of all funding rates"""
        logger.info("Forcing funding rate update")
        await self._update_funding_rates()
        await self._calculate_spreads()
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get status summary"""
        total_pairs = len(self.trading_pairs)
        active_pairs = len([p for p in self.trading_pairs if p.enabled])
        monitored_pairs = len(self.spreads)
        profitable_opportunities = len(self.get_profitable_opportunities())
        
        return {
            "running": self._running,
            "total_pairs": total_pairs,
            "active_pairs": active_pairs,
            "monitored_pairs": monitored_pairs,
            "profitable_opportunities": profitable_opportunities,
            "last_update": max(
                (spread.timestamp for spread in self.spreads.values()),
                default=None
            )
        }