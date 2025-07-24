"""Trade Executor for arbitrage opportunities"""

import asyncio
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
from loguru import logger

from .opportunity_detector import ArbitrageOpportunity, OpportunityStatus
from ..exchanges.base_exchange import (
    BaseExchange, Order, OrderSide, OrderType, OrderStatus
)
from ..config.config_manager import RiskManagementConfig
from ..utils.helpers import round_to_precision, get_current_timestamp


class ExecutionStatus(Enum):
    """Execution status enumeration"""
    PENDING = "pending"
    PARTIAL = "partial"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TradeExecution:
    """Trade execution record"""
    id: str
    opportunity_id: str
    symbol: str
    status: ExecutionStatus
    
    # Orders
    reya_order: Optional[Order]
    hyperliquid_order: Optional[Order]
    
    # Execution details
    planned_size: float
    executed_size: float
    average_entry_price_reya: float
    average_entry_price_hl: float
    
    # Timing
    started_at: datetime
    completed_at: Optional[datetime]
    
    # Results
    realized_pnl: float
    execution_cost: float
    slippage: float
    
    # Metadata
    notes: str = ""
    error_message: str = ""


class TradeExecutor:
    """Execute arbitrage trades across exchanges"""
    
    def __init__(
        self,
        reya_client: BaseExchange,
        hyperliquid_client: BaseExchange,
        risk_config: RiskManagementConfig,
        dry_run: bool = True
    ):
        self.reya_client = reya_client
        self.hyperliquid_client = hyperliquid_client
        self.risk_config = risk_config
        self.dry_run = dry_run
        
        # Execution tracking
        self.executions: Dict[str, TradeExecution] = {}
        self.execution_queue: List[str] = []  # Queue of opportunity IDs
        
        # Execution settings
        self.max_slippage = 0.005  # 0.5% max slippage
        self.order_timeout = 30  # 30 seconds order timeout
        self.execution_timeout = 120  # 2 minutes total execution timeout
        
        # Control flags
        self._executing = False
        
        logger.info(f"Initialized TradeExecutor (dry_run={dry_run})")
    
    async def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> Optional[TradeExecution]:
        """Execute an arbitrage opportunity"""
        if self._executing:
            logger.warning(f"Executor busy, queueing opportunity {opportunity.id}")
            self.execution_queue.append(opportunity.id)
            return None
        
        self._executing = True
        
        try:
            # Validate opportunity before execution
            if not await self._pre_execution_validation(opportunity):
                return None
            
            # Create execution record
            execution = self._create_execution_record(opportunity)
            self.executions[execution.id] = execution
            
            # Update opportunity status
            opportunity.status = OpportunityStatus.EXECUTING
            opportunity.executed_at = datetime.now(timezone.utc)
            
            logger.info(f"Starting execution for opportunity {opportunity.id}")
            
            if self.dry_run:
                # Simulate execution
                await self._simulate_execution(execution, opportunity)
            else:
                # Real execution
                await self._execute_real_trades(execution, opportunity)
            
            return execution
            
        except Exception as e:
            logger.error(f"Error executing opportunity {opportunity.id}: {e}")
            if execution:
                execution.status = ExecutionStatus.FAILED
                execution.error_message = str(e)
            return None
            
        finally:
            self._executing = False
            await self._process_queue()
    
    async def _pre_execution_validation(self, opportunity: ArbitrageOpportunity) -> bool:
        """Validate opportunity before execution"""
        try:
            # Check if opportunity is still valid
            if opportunity.status != OpportunityStatus.VALIDATED:
                logger.warning(f"Opportunity {opportunity.id} not validated")
                return False
            
            # Check if opportunity has expired
            if opportunity.expires_at and datetime.now(timezone.utc) > opportunity.expires_at:
                logger.warning(f"Opportunity {opportunity.id} has expired")
                opportunity.status = OpportunityStatus.EXPIRED
                return False
            
            # Check exchange connectivity
            reya_health = await self.reya_client.health_check()
            hl_health = await self.hyperliquid_client.health_check()
            
            if not reya_health or not hl_health:
                logger.error("Exchange health check failed")
                return False
            
            # Check available balances
            if not await self._check_sufficient_balance(opportunity):
                logger.error(f"Insufficient balance for opportunity {opportunity.id}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Pre-execution validation failed: {e}")
            return False
    
    async def _check_sufficient_balance(self, opportunity: ArbitrageOpportunity) -> bool:
        """Check if we have sufficient balance for the trade"""
        try:
            # Get balances from both exchanges
            reya_balances = await self.reya_client.get_balance()
            hl_balances = await self.hyperliquid_client.get_balance()
            
            # Calculate required margin (simplified)
            required_margin = opportunity.recommended_size * 0.1  # Assume 10x leverage
            
            # Check Reya balance
            reya_available = sum(
                b.available for b in reya_balances 
                if b.currency in ['USD', 'USDT', 'rUSD']
            )
            
            # Check Hyperliquid balance
            hl_available = sum(
                b.available for b in hl_balances 
                if b.currency in ['USD', 'USDT']
            )
            
            return reya_available >= required_margin and hl_available >= required_margin
            
        except Exception as e:
            logger.error(f"Error checking balance: {e}")
            return False
    
    def _create_execution_record(self, opportunity: ArbitrageOpportunity) -> TradeExecution:
        """Create execution record"""
        execution_id = f"exec_{opportunity.id}_{int(get_current_timestamp())}"
        
        return TradeExecution(
            id=execution_id,
            opportunity_id=opportunity.id,
            symbol=opportunity.symbol,
            status=ExecutionStatus.PENDING,
            reya_order=None,
            hyperliquid_order=None,
            planned_size=opportunity.recommended_size,
            executed_size=0.0,
            average_entry_price_reya=0.0,
            average_entry_price_hl=0.0,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            realized_pnl=0.0,
            execution_cost=0.0,
            slippage=0.0
        )
    
    async def _simulate_execution(self, execution: TradeExecution, opportunity: ArbitrageOpportunity) -> None:
        """Simulate trade execution for dry run"""
        logger.info(f"SIMULATION: Executing {opportunity.symbol} arbitrage")
        logger.info(f"SIMULATION: {opportunity.reya_action} {execution.planned_size} on Reya")
        logger.info(f"SIMULATION: {opportunity.hyperliquid_action} {execution.planned_size} on Hyperliquid")
        
        # Simulate execution delay
        await asyncio.sleep(2)
        
        # Simulate successful execution
        execution.status = ExecutionStatus.COMPLETED
        execution.executed_size = execution.planned_size
        execution.average_entry_price_reya = 50000.0  # Mock price
        execution.average_entry_price_hl = 50000.0  # Mock price
        execution.completed_at = datetime.now(timezone.utc)
        execution.realized_pnl = opportunity.expected_profit * 0.8  # 80% of expected
        execution.execution_cost = execution.planned_size * 0.001  # 0.1% cost
        execution.slippage = 0.002  # 0.2% slippage
        
        opportunity.status = OpportunityStatus.EXECUTED
        
        logger.info(f"SIMULATION: Execution completed with PnL: ${execution.realized_pnl:.2f}")
    
    async def _execute_real_trades(self, execution: TradeExecution, opportunity: ArbitrageOpportunity) -> None:
        """Execute real trades on exchanges"""
        try:
            # Determine order sides
            reya_side = OrderSide.BUY if opportunity.reya_action == "long" else OrderSide.SELL
            hl_side = OrderSide.BUY if opportunity.hyperliquid_action == "long" else OrderSide.SELL
            
            # Execute trades simultaneously
            reya_task = self._place_order(
                self.reya_client,
                opportunity.symbol,
                reya_side,
                execution.planned_size
            )
            
            hl_task = self._place_order(
                self.hyperliquid_client,
                opportunity.symbol,
                hl_side,
                execution.planned_size
            )
            
            # Wait for both orders
            reya_order, hl_order = await asyncio.gather(
                reya_task, hl_task, return_exceptions=True
            )
            
            # Handle order results
            if isinstance(reya_order, Exception):
                logger.error(f"Reya order failed: {reya_order}")
                reya_order = None
            
            if isinstance(hl_order, Exception):
                logger.error(f"Hyperliquid order failed: {hl_order}")
                hl_order = None
            
            execution.reya_order = reya_order
            execution.hyperliquid_order = hl_order
            
            # Monitor order execution
            await self._monitor_execution(execution)
            
            # Calculate final results
            await self._calculate_execution_results(execution)
            
        except Exception as e:
            logger.error(f"Real trade execution failed: {e}")
            execution.status = ExecutionStatus.FAILED
            execution.error_message = str(e)
            
            # Try to cancel any open orders
            await self._cleanup_failed_execution(execution)
    
    async def _place_order(
        self,
        exchange: BaseExchange,
        symbol: str,
        side: OrderSide,
        amount: float
    ) -> Optional[Order]:
        """Place order on exchange"""
        try:
            # Use market orders for immediate execution
            order = await exchange.place_order(
                symbol=symbol,
                side=side,
                amount=amount,
                order_type=OrderType.MARKET
            )
            
            if order:
                logger.info(f"Order placed on {exchange.name}: {order.id}")
            
            return order
            
        except Exception as e:
            logger.error(f"Failed to place order on {exchange.name}: {e}")
            raise
    
    async def _monitor_execution(self, execution: TradeExecution) -> None:
        """Monitor order execution progress"""
        start_time = datetime.now(timezone.utc)
        timeout = start_time.timestamp() + self.execution_timeout
        
        while datetime.now(timezone.utc).timestamp() < timeout:
            try:
                # Check order statuses
                reya_filled = await self._check_order_status(execution.reya_order, self.reya_client)
                hl_filled = await self._check_order_status(execution.hyperliquid_order, self.hyperliquid_client)
                
                # Update execution status
                if reya_filled and hl_filled:
                    execution.status = ExecutionStatus.COMPLETED
                    execution.completed_at = datetime.now(timezone.utc)
                    break
                elif reya_filled or hl_filled:
                    execution.status = ExecutionStatus.PARTIAL
                
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Error monitoring execution: {e}")
                break
        
        # Handle timeout
        if execution.status != ExecutionStatus.COMPLETED:
            logger.warning(f"Execution {execution.id} timed out")
            await self._handle_execution_timeout(execution)
    
    async def _check_order_status(self, order: Optional[Order], exchange: BaseExchange) -> bool:
        """Check if order is filled"""
        if not order:
            return False
        
        try:
            updated_order = await exchange.get_order_status(order.id)
            if updated_order and updated_order.status == OrderStatus.FILLED:
                # Update order details
                order.status = updated_order.status
                order.filled_amount = updated_order.filled_amount
                return True
        except Exception as e:
            logger.error(f"Error checking order status: {e}")
        
        return False
    
    async def _handle_execution_timeout(self, execution: TradeExecution) -> None:
        """Handle execution timeout"""
        # Try to cancel unfilled orders
        if execution.reya_order and execution.reya_order.status != OrderStatus.FILLED:
            try:
                await self.reya_client.cancel_order(execution.reya_order.id)
            except Exception as e:
                logger.error(f"Failed to cancel Reya order: {e}")
        
        if execution.hyperliquid_order and execution.hyperliquid_order.status != OrderStatus.FILLED:
            try:
                await self.hyperliquid_client.cancel_order(execution.hyperliquid_order.id)
            except Exception as e:
                logger.error(f"Failed to cancel Hyperliquid order: {e}")
        
        execution.status = ExecutionStatus.FAILED
        execution.error_message = "Execution timeout"
    
    async def _calculate_execution_results(self, execution: TradeExecution) -> None:
        """Calculate execution results"""
        try:
            total_executed = 0.0
            total_cost = 0.0
            
            # Calculate from Reya order
            if execution.reya_order and execution.reya_order.filled_amount > 0:
                total_executed += execution.reya_order.filled_amount
                if execution.reya_order.price:
                    execution.average_entry_price_reya = execution.reya_order.price
                total_cost += execution.reya_order.filled_amount * 0.0005  # Estimated fee
            
            # Calculate from Hyperliquid order
            if execution.hyperliquid_order and execution.hyperliquid_order.filled_amount > 0:
                total_executed += execution.hyperliquid_order.filled_amount
                if execution.hyperliquid_order.price:
                    execution.average_entry_price_hl = execution.hyperliquid_order.price
                total_cost += execution.hyperliquid_order.filled_amount * 0.0005  # Estimated fee
            
            execution.executed_size = total_executed / 2  # Average of both sides
            execution.execution_cost = total_cost
            
            # Calculate slippage (simplified)
            if execution.average_entry_price_reya > 0 and execution.average_entry_price_hl > 0:
                price_diff = abs(execution.average_entry_price_reya - execution.average_entry_price_hl)
                avg_price = (execution.average_entry_price_reya + execution.average_entry_price_hl) / 2
                execution.slippage = price_diff / avg_price if avg_price > 0 else 0
            
            # TODO: Calculate realized PnL (requires position tracking)
            execution.realized_pnl = 0.0  # Placeholder
            
        except Exception as e:
            logger.error(f"Error calculating execution results: {e}")
    
    async def _cleanup_failed_execution(self, execution: TradeExecution) -> None:
        """Cleanup after failed execution"""
        # Cancel any remaining orders
        if execution.reya_order:
            try:
                await self.reya_client.cancel_order(execution.reya_order.id)
            except Exception:
                pass
        
        if execution.hyperliquid_order:
            try:
                await self.hyperliquid_client.cancel_order(execution.hyperliquid_order.id)
            except Exception:
                pass
    
    async def _process_queue(self) -> None:
        """Process queued executions"""
        if self.execution_queue and not self._executing:
            opportunity_id = self.execution_queue.pop(0)
            logger.info(f"Processing queued opportunity: {opportunity_id}")
            # Note: Would need access to opportunity detector to get opportunity object
    
    def get_execution_by_id(self, execution_id: str) -> Optional[TradeExecution]:
        """Get execution by ID"""
        return self.executions.get(execution_id)
    
    def get_executions_for_symbol(self, symbol: str) -> List[TradeExecution]:
        """Get all executions for a symbol"""
        return [exec for exec in self.executions.values() if exec.symbol == symbol]
    
    def get_active_executions(self) -> List[TradeExecution]:
        """Get all active executions"""
        return [
            exec for exec in self.executions.values()
            if exec.status in [ExecutionStatus.PENDING, ExecutionStatus.PARTIAL]
        ]
    
    def get_execution_statistics(self) -> Dict[str, Any]:
        """Get execution statistics"""
        total_executions = len(self.executions)
        completed_executions = len([
            exec for exec in self.executions.values()
            if exec.status == ExecutionStatus.COMPLETED
        ])
        
        total_pnl = sum(exec.realized_pnl for exec in self.executions.values())
        total_cost = sum(exec.execution_cost for exec in self.executions.values())
        
        success_rate = (completed_executions / total_executions) if total_executions > 0 else 0.0
        
        return {
            "total_executions": total_executions,
            "completed_executions": completed_executions,
            "success_rate": success_rate,
            "total_pnl": total_pnl,
            "total_cost": total_cost,
            "net_pnl": total_pnl - total_cost,
            "average_slippage": sum(
                exec.slippage for exec in self.executions.values()
            ) / total_executions if total_executions > 0 else 0.0
        }