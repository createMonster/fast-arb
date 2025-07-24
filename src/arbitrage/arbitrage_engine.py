"""Main Arbitrage Engine - Orchestrates the entire arbitrage process"""

import asyncio
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
from loguru import logger

from .funding_monitor import FundingRateMonitor, FundingRateSpread
from .opportunity_detector import OpportunityDetector, ArbitrageOpportunity, OpportunityStatus
from .trade_executor import TradeExecutor, TradeExecution, ExecutionStatus
from ..exchanges.reya_client import ReyaClient
from ..exchanges.hyperliquid_client import HyperliquidClient
from ..config.config_manager import ConfigManager
from ..utils.helpers import get_current_timestamp


class EngineStatus(Enum):
    """Engine status enumeration"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class EngineStats:
    """Engine statistics"""
    uptime_seconds: float
    opportunities_detected: int
    opportunities_executed: int
    total_pnl: float
    success_rate: float
    last_opportunity_time: Optional[datetime]
    active_positions: int
    errors_count: int


class ArbitrageEngine:
    """Main arbitrage engine that orchestrates the entire process"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        # Load configuration
        self.config_manager = ConfigManager(config_path)
        
        # Get specific configurations
        self.reya_config = self.config_manager.get_reya_config()
        self.hyperliquid_config = self.config_manager.get_hyperliquid_config()
        self.general_config = self.config_manager.get_general_config()
        self.arbitrage_config = self.config_manager.get_arbitrage_config()
        self.risk_config = self.config_manager.get_risk_management_config()
        self.trading_pairs = self.config_manager.get_trading_pairs()
        
        # Initialize components
        self.reya_client: Optional[ReyaClient] = None
        self.hyperliquid_client: Optional[HyperliquidClient] = None
        self.funding_monitor: Optional[FundingRateMonitor] = None
        self.opportunity_detector: Optional[OpportunityDetector] = None
        self.trade_executor: Optional[TradeExecutor] = None
        
        # Engine state
        self.status = EngineStatus.STOPPED
        self.start_time: Optional[datetime] = None
        self.stop_event = asyncio.Event()
        
        # Statistics
        self.stats = EngineStats(
            uptime_seconds=0.0,
            opportunities_detected=0,
            opportunities_executed=0,
            total_pnl=0.0,
            success_rate=0.0,
            last_opportunity_time=None,
            active_positions=0,
            errors_count=0
        )
        
        # Event callbacks
        self.on_opportunity_detected: Optional[Callable] = None
        self.on_trade_executed: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        
        # Control flags
        self._running_tasks: List[asyncio.Task] = []
        
        logger.info("Arbitrage Engine initialized")
    
    async def initialize(self) -> bool:
        """Initialize all components"""
        try:
            self.status = EngineStatus.STARTING
            logger.info("Initializing arbitrage engine components...")
            
            # Initialize exchange clients
            await self._initialize_exchanges()
            
            # Initialize monitoring and detection components
            await self._initialize_components()
            
            # Setup event handlers
            self._setup_event_handlers()
            
            logger.info("All components initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize engine: {e}")
            self.status = EngineStatus.ERROR
            return False
    
    async def _initialize_exchanges(self) -> None:
        """Initialize exchange clients"""
        # Initialize Reya client
        reya_config_dict = {
            'private_key': self.reya_config.private_key,
            'rpc_url': self.reya_config.rpc_url,
            'websocket_url': self.reya_config.websocket_url,
            'chain_id': self.reya_config.chain_id,
            'account_id': self.reya_config.account_id
        }
        self.reya_client = ReyaClient(reya_config_dict)
        
        # Initialize Hyperliquid client
        hyperliquid_config_dict = {
            'private_key': self.hyperliquid_config.private_key,
            'api_url': self.hyperliquid_config.api_url,
            'testnet': self.hyperliquid_config.testnet
        }
        self.hyperliquid_client = HyperliquidClient(hyperliquid_config_dict)
        
        # Connect to exchanges
        logger.info("Connecting to exchanges...")
        
        reya_connected = await self.reya_client.connect()
        hl_connected = await self.hyperliquid_client.connect()
        
        # Log connection status
        if reya_connected:
            logger.info("✅ Connected to Reya Network")
        else:
            logger.warning("⚠️ Failed to connect to Reya Network - some features may be limited")
        
        if hl_connected:
            logger.info("✅ Connected to Hyperliquid")
        else:
            logger.warning("⚠️ Failed to connect to Hyperliquid - some features may be limited")
        
        # For development/testing purposes, allow engine to start even if connections fail
        # In production, you might want to require at least one successful connection
        if not reya_connected and not hl_connected:
            logger.warning("⚠️ No exchange connections established - running in offline mode")
        
        logger.info(f"Exchange connections: Reya={reya_connected}, Hyperliquid={hl_connected}")
    
    async def _initialize_components(self) -> None:
        """Initialize monitoring and detection components"""
        # Initialize funding rate monitor
        self.funding_monitor = FundingRateMonitor(
            reya_client=self.reya_client,
            hyperliquid_client=self.hyperliquid_client,
            trading_pairs=self.trading_pairs,
            update_interval=self.arbitrage_config.funding_rate.get('check_interval', 60)
        )
        
        # Initialize opportunity detector
        self.opportunity_detector = OpportunityDetector(
            reya_client=self.reya_client,
            hyperliquid_client=self.hyperliquid_client,
            trading_pairs=self.trading_pairs,
            risk_config=self.risk_config
        )
        
        # Initialize trade executor
        self.trade_executor = TradeExecutor(
            reya_client=self.reya_client,
            hyperliquid_client=self.hyperliquid_client,
            risk_config=self.risk_config,
            dry_run=self.general_config.dry_run
        )
        
        logger.info("All monitoring components initialized")
    
    def _setup_event_handlers(self) -> None:
        """Setup event handlers between components"""
        # Funding monitor -> Opportunity detector
        self.funding_monitor.on_spread_update = self._handle_spread_update
        self.funding_monitor.on_arbitrage_opportunity = self._handle_funding_opportunity
        
        # Opportunity detector -> Trade executor
        self.opportunity_detector.on_opportunity_validated = self._handle_validated_opportunity
        
        logger.info("Event handlers configured")
    
    async def start(self) -> bool:
        """Start the arbitrage engine"""
        if self.status == EngineStatus.RUNNING:
            logger.warning("Engine is already running")
            return True
        
        try:
            # Initialize if not done
            if self.status != EngineStatus.STARTING:
                if not await self.initialize():
                    return False
            
            self.status = EngineStatus.RUNNING
            self.start_time = datetime.now(timezone.utc)
            self.stop_event.clear()
            
            logger.info("Starting arbitrage engine...")
            
            # Start all monitoring tasks
            await self._start_monitoring_tasks()
            
            logger.info("🚀 Arbitrage engine is now running!")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start engine: {e}")
            self.status = EngineStatus.ERROR
            return False
    
    async def _start_monitoring_tasks(self) -> None:
        """Start all monitoring tasks"""
        # Start funding rate monitoring
        funding_task = asyncio.create_task(
            self.funding_monitor.start_monitoring(),
            name="funding_monitor"
        )
        self._running_tasks.append(funding_task)
        
        # Note: OpportunityDetector works reactively, no separate task needed
        
        # Start statistics update task
        stats_task = asyncio.create_task(
            self._update_statistics_loop(),
            name="statistics_updater"
        )
        self._running_tasks.append(stats_task)
        
        # Start health check task
        health_task = asyncio.create_task(
            self._health_check_loop(),
            name="health_checker"
        )
        self._running_tasks.append(health_task)
        
        logger.info(f"Started {len(self._running_tasks)} monitoring tasks")
    
    async def stop(self) -> None:
        """Stop the arbitrage engine"""
        if self.status == EngineStatus.STOPPED:
            logger.warning("Engine is already stopped")
            return
        
        logger.info("Stopping arbitrage engine...")
        self.status = EngineStatus.STOPPING
        
        # Signal stop to all tasks
        self.stop_event.set()
        
        # Stop monitoring components
        if self.funding_monitor:
            await self.funding_monitor.stop_monitoring()
        
        # Note: OpportunityDetector doesn't need explicit stopping
        
        # Cancel all running tasks
        for task in self._running_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks, return_exceptions=True)
        
        self._running_tasks.clear()
        
        # Disconnect from exchanges
        if self.reya_client:
            await self.reya_client.disconnect()
        
        if self.hyperliquid_client:
            await self.hyperliquid_client.disconnect()
        
        self.status = EngineStatus.STOPPED
        logger.info("✅ Arbitrage engine stopped")
    
    async def _handle_spread_update(self, spread: FundingRateSpread) -> None:
        """Handle funding rate spread updates"""
        logger.debug(f"Spread update for {spread.symbol}: {spread.spread_percentage:.4f}%")
        
        # Update statistics
        self.stats.last_opportunity_time = datetime.now(timezone.utc)
    
    async def _handle_funding_opportunity(self, spread: FundingRateSpread) -> None:
        """Handle potential funding rate opportunities"""
        logger.info(f"Funding opportunity detected for {spread.symbol}: {spread.spread_percentage:.4f}%")
        
        # Let opportunity detector validate this
        if self.opportunity_detector:
            await self.opportunity_detector.analyze_spread(spread)
    
    async def _handle_validated_opportunity(self, opportunity: ArbitrageOpportunity) -> None:
        """Handle validated arbitrage opportunities"""
        logger.info(f"Validated opportunity: {opportunity.symbol} - Expected profit: ${opportunity.expected_profit:.2f}")
        
        # Update statistics
        self.stats.opportunities_detected += 1
        
        # Execute if conditions are met
        if self._should_execute_opportunity(opportunity):
            execution = await self.trade_executor.execute_opportunity(opportunity)
            
            if execution:
                await self._handle_trade_execution(execution)
        
        # Call external callback if set
        if self.on_opportunity_detected:
            try:
                await self.on_opportunity_detected(opportunity)
            except Exception as e:
                logger.error(f"Error in opportunity callback: {e}")
    
    def _should_execute_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Determine if opportunity should be executed"""
        # Check if we're in simulation mode
        if self.general_config.dry_run:
            return True
        
        # Check minimum profit threshold
        if opportunity.expected_profit < self.config.risk_management.min_trade_amount:
            logger.debug(f"Opportunity profit too low: ${opportunity.expected_profit:.2f}")
            return False
        
        # Check risk/reward ratio
        if opportunity.risk_reward_ratio < 2.0:  # Minimum 2:1 ratio
            logger.debug(f"Risk/reward ratio too low: {opportunity.risk_reward_ratio:.2f}")
            return False
        
        # Check if we have conflicting positions
        active_executions = self.trade_executor.get_executions_for_symbol(opportunity.symbol)
        if any(exec.status in [ExecutionStatus.PENDING, ExecutionStatus.PARTIAL] for exec in active_executions):
            logger.debug(f"Active execution exists for {opportunity.symbol}")
            return False
        
        return True
    
    async def _handle_trade_execution(self, execution: TradeExecution) -> None:
        """Handle trade execution results"""
        if execution.status == ExecutionStatus.COMPLETED:
            logger.info(f"Trade executed successfully: {execution.id} - PnL: ${execution.realized_pnl:.2f}")
            self.stats.opportunities_executed += 1
            self.stats.total_pnl += execution.realized_pnl
        else:
            logger.warning(f"Trade execution failed: {execution.id} - Status: {execution.status}")
            self.stats.errors_count += 1
        
        # Update success rate
        if self.stats.opportunities_detected > 0:
            self.stats.success_rate = self.stats.opportunities_executed / self.stats.opportunities_detected
        
        # Call external callback if set
        if self.on_trade_executed:
            try:
                await self.on_trade_executed(execution)
            except Exception as e:
                logger.error(f"Error in trade execution callback: {e}")
    
    async def _update_statistics_loop(self) -> None:
        """Update engine statistics periodically"""
        while not self.stop_event.is_set():
            try:
                await self._update_statistics()
                await asyncio.sleep(30)  # Update every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error updating statistics: {e}")
                await asyncio.sleep(30)
    
    async def _update_statistics(self) -> None:
        """Update engine statistics"""
        if self.start_time:
            self.stats.uptime_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        # Update active positions count
        if self.trade_executor:
            active_executions = self.trade_executor.get_active_executions()
            self.stats.active_positions = len(active_executions)
    
    async def _health_check_loop(self) -> None:
        """Perform periodic health checks"""
        while not self.stop_event.is_set():
            try:
                await self._perform_health_check()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(60)
    
    async def _perform_health_check(self) -> None:
        """Perform health check on all components"""
        try:
            # Check exchange connectivity
            if self.reya_client:
                reya_health = await self.reya_client.health_check()
                if not reya_health:
                    logger.warning("Reya client health check failed")
            
            if self.hyperliquid_client:
                hl_health = await self.hyperliquid_client.health_check()
                if not hl_health:
                    logger.warning("Hyperliquid client health check failed")
            
            # Check component status
            if self.funding_monitor and not self.funding_monitor.is_running():
                logger.warning("Funding monitor is not active")
            
            # Opportunity detector is always active when initialized
            if not self.opportunity_detector:
                logger.warning("Opportunity detector is not initialized")
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self.stats.errors_count += 1
    
    # Public API methods
    
    def get_status(self) -> EngineStatus:
        """Get current engine status"""
        return self.status
    
    def get_statistics(self) -> EngineStats:
        """Get engine statistics"""
        return self.stats
    
    def get_active_opportunities(self) -> List[ArbitrageOpportunity]:
        """Get currently active opportunities"""
        if self.opportunity_detector:
            return self.opportunity_detector.get_active_opportunities()
        return []
    
    def get_recent_executions(self, limit: int = 10) -> List[TradeExecution]:
        """Get recent trade executions"""
        if self.trade_executor:
            executions = list(self.trade_executor.executions.values())
            executions.sort(key=lambda x: x.started_at, reverse=True)
            return executions[:limit]
        return []
    
    def get_current_spreads(self) -> Dict[str, FundingRateSpread]:
        """Get current funding rate spreads"""
        if self.funding_monitor:
            return self.funding_monitor.get_current_spreads()
        return {}
    
    async def force_opportunity_check(self) -> None:
        """Force an immediate opportunity check"""
        if self.opportunity_detector:
            await self.opportunity_detector.force_check()
    
    async def emergency_stop(self) -> None:
        """Emergency stop - cancel all orders and positions"""
        logger.warning("🚨 EMERGENCY STOP INITIATED")
        
        # Cancel all active executions
        if self.trade_executor:
            active_executions = self.trade_executor.get_active_executions()
            for execution in active_executions:
                try:
                    # Cancel orders
                    if execution.reya_order:
                        await self.reya_client.cancel_order(execution.reya_order.id)
                    if execution.hyperliquid_order:
                        await self.hyperliquid_client.cancel_order(execution.hyperliquid_order.id)
                except Exception as e:
                    logger.error(f"Error cancelling orders for {execution.id}: {e}")
        
        # Stop the engine
        await self.stop()
        
        logger.warning("🛑 Emergency stop completed")