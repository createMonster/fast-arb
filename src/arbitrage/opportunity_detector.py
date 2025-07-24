"""Arbitrage Opportunity Detector"""

import asyncio
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from enum import Enum
from loguru import logger

from .funding_monitor import FundingRateSpread
from ..exchanges.base_exchange import BaseExchange, Position
from ..config.config_manager import TradingPair, RiskManagementConfig
from ..utils.helpers import (
    calculate_position_size,
    safe_float,
    round_to_precision
)


class OpportunityType(Enum):
    """Types of arbitrage opportunities"""
    FUNDING_RATE = "funding_rate"
    PRICE_SPREAD = "price_spread"
    BASIS_SPREAD = "basis_spread"


class OpportunityStatus(Enum):
    """Status of arbitrage opportunities"""
    DETECTED = "detected"
    VALIDATED = "validated"
    EXECUTING = "executing"
    EXECUTED = "executed"
    EXPIRED = "expired"
    REJECTED = "rejected"


@dataclass
class ArbitrageOpportunity:
    """Arbitrage opportunity data structure"""
    id: str
    type: OpportunityType
    symbol: str
    status: OpportunityStatus
    
    # Spread information
    reya_rate: float
    hyperliquid_rate: float
    spread: float
    spread_percentage: float
    direction: str  # "long_reya_short_hl" or "short_reya_long_hl"
    
    # Position sizing
    recommended_size: float
    max_position_size: float
    
    # Risk metrics
    expected_profit: float
    max_loss: float
    risk_reward_ratio: float
    
    # Timing
    detected_at: datetime
    expires_at: Optional[datetime]
    executed_at: Optional[datetime]
    
    # Execution details
    reya_action: str  # "long" or "short"
    hyperliquid_action: str  # "long" or "short"
    
    # Metadata
    confidence_score: float
    notes: str = ""


class OpportunityDetector:
    """Detect and validate arbitrage opportunities"""
    
    def __init__(
        self,
        reya_client: BaseExchange,
        hyperliquid_client: BaseExchange,
        trading_pairs: List[TradingPair],
        risk_config: RiskManagementConfig
    ):
        self.reya_client = reya_client
        self.hyperliquid_client = hyperliquid_client
        self.trading_pairs = trading_pairs
        self.risk_config = risk_config
        
        # Opportunity storage
        self.opportunities: Dict[str, ArbitrageOpportunity] = {}
        self.opportunity_history: List[ArbitrageOpportunity] = []
        
        # Current positions
        self.current_positions: Dict[str, Dict[str, Position]] = {}
        
        # Configuration
        self.min_confidence_score = 0.7
        self.opportunity_timeout = timedelta(minutes=5)
        
        logger.info("Initialized OpportunityDetector")
    
    async def analyze_spread(self, spread: FundingRateSpread) -> Optional[ArbitrageOpportunity]:
        """Analyze a funding rate spread for arbitrage opportunities"""
        try:
            # Find trading pair configuration
            pair_config = self._get_pair_config(spread.symbol)
            if not pair_config:
                logger.warning(f"No configuration found for {spread.symbol}")
                return None
            
            # Check if spread meets minimum threshold
            if spread.spread < pair_config.min_funding_rate_diff:
                return None
            
            # Calculate opportunity metrics
            opportunity = await self._create_opportunity(spread, pair_config)
            
            # Validate opportunity
            if await self._validate_opportunity(opportunity):
                # Store opportunity
                self.opportunities[opportunity.id] = opportunity
                
                logger.info(
                    f"New arbitrage opportunity: {opportunity.symbol} "
                    f"spread={opportunity.spread:.4f}% "
                    f"confidence={opportunity.confidence_score:.2f}"
                )
                
                return opportunity
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing spread for {spread.symbol}: {e}")
            return None
    
    async def _create_opportunity(
        self,
        spread: FundingRateSpread,
        pair_config: TradingPair
    ) -> ArbitrageOpportunity:
        """Create an arbitrage opportunity from spread data"""
        
        # Generate unique ID
        opportunity_id = f"{spread.symbol}_{int(spread.timestamp.timestamp())}"
        
        # Determine actions based on direction
        if spread.direction == "short_reya_long_hl":
            reya_action = "short"
            hyperliquid_action = "long"
        else:
            reya_action = "long"
            hyperliquid_action = "short"
        
        # Calculate position sizing
        recommended_size, max_size = await self._calculate_position_sizing(
            spread.symbol, spread.spread, pair_config
        )
        
        # Calculate profit/loss estimates
        expected_profit = self._estimate_profit(spread, recommended_size)
        max_loss = self._estimate_max_loss(spread, recommended_size)
        risk_reward_ratio = abs(expected_profit / max_loss) if max_loss != 0 else float('inf')
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(spread, pair_config)
        
        # Set expiration time
        expires_at = spread.timestamp + self.opportunity_timeout
        
        return ArbitrageOpportunity(
            id=opportunity_id,
            type=OpportunityType.FUNDING_RATE,
            symbol=spread.symbol,
            status=OpportunityStatus.DETECTED,
            reya_rate=spread.reya_rate,
            hyperliquid_rate=spread.hyperliquid_rate,
            spread=spread.spread,
            spread_percentage=spread.spread_percentage,
            direction=spread.direction,
            recommended_size=recommended_size,
            max_position_size=max_size,
            expected_profit=expected_profit,
            max_loss=max_loss,
            risk_reward_ratio=risk_reward_ratio,
            detected_at=spread.timestamp,
            expires_at=expires_at,
            executed_at=None,
            reya_action=reya_action,
            hyperliquid_action=hyperliquid_action,
            confidence_score=confidence_score
        )
    
    async def _calculate_position_sizing(
        self,
        symbol: str,
        spread: float,
        pair_config: TradingPair
    ) -> Tuple[float, float]:
        """Calculate recommended and maximum position sizes"""
        
        # Get current account balances
        reya_balances = await self.reya_client.get_balance()
        hl_balances = await self.hyperliquid_client.get_balance()
        
        # Calculate available capital (simplified - using USD/USDT balances)
        reya_capital = sum(b.available for b in reya_balances if b.currency in ['USD', 'USDT', 'rUSD'])
        hl_capital = sum(b.available for b in hl_balances if b.currency in ['USD', 'USDT'])
        
        # Use minimum available capital
        available_capital = min(reya_capital, hl_capital)
        
        # Apply risk management limits
        max_total_position = min(available_capital, self.risk_config.max_total_position)
        max_pair_position = min(max_total_position, pair_config.max_position)
        
        # Calculate recommended size based on spread and risk
        # Higher spread = larger position (up to limits)
        spread_factor = min(spread / 1.0, 1.0)  # Normalize to 1% max
        recommended_size = max_pair_position * spread_factor * 0.5  # Conservative sizing
        
        # Ensure minimum trade amount
        recommended_size = max(recommended_size, self.risk_config.min_trade_amount)
        
        # Ensure we don't exceed limits
        recommended_size = min(recommended_size, max_pair_position)
        
        return round_to_precision(recommended_size, 2), round_to_precision(max_pair_position, 2)
    
    def _estimate_profit(self, spread: FundingRateSpread, position_size: float) -> float:
        """Estimate expected profit from the arbitrage"""
        # Funding rates are typically annualized
        # Convert to 8-hour funding period (typical for perpetuals)
        funding_period_hours = 8
        annual_hours = 365 * 24
        
        period_spread = spread.spread * (funding_period_hours / annual_hours)
        expected_profit = position_size * (period_spread / 100)
        
        return round_to_precision(expected_profit, 4)
    
    def _estimate_max_loss(self, spread: FundingRateSpread, position_size: float) -> float:
        """Estimate maximum potential loss"""
        # Maximum loss could occur if:
        # 1. Funding rates reverse completely
        # 2. Price movements against positions
        # 3. Execution slippage
        
        # Conservative estimate: 2x the expected profit as max loss
        expected_profit = self._estimate_profit(spread, position_size)
        max_loss = abs(expected_profit) * 2
        
        # Add execution costs (estimated)
        execution_cost = position_size * 0.001  # 0.1% total execution cost
        max_loss += execution_cost
        
        return round_to_precision(max_loss, 4)
    
    def _calculate_confidence_score(self, spread: FundingRateSpread, pair_config: TradingPair) -> float:
        """Calculate confidence score for the opportunity"""
        score = 0.0
        
        # Spread magnitude (higher spread = higher confidence)
        spread_score = min(spread.spread / 2.0, 1.0)  # Normalize to 2% max
        score += spread_score * 0.4
        
        # Spread vs minimum threshold
        threshold_score = min(spread.spread / pair_config.min_funding_rate_diff, 2.0) / 2.0
        score += threshold_score * 0.3
        
        # Market conditions (placeholder - could add volatility, volume checks)
        market_score = 0.7  # Default moderate confidence
        score += market_score * 0.2
        
        # Historical success rate (placeholder)
        history_score = 0.8  # Default good historical performance
        score += history_score * 0.1
        
        return min(score, 1.0)
    
    async def _validate_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Validate an arbitrage opportunity"""
        try:
            # Check confidence score
            if opportunity.confidence_score < self.min_confidence_score:
                opportunity.notes += "Low confidence score; "
                return False
            
            # Check risk/reward ratio
            if opportunity.risk_reward_ratio < 1.5:
                opportunity.notes += "Poor risk/reward ratio; "
                return False
            
            # Check if we already have positions in this symbol
            if await self._has_conflicting_positions(opportunity.symbol):
                opportunity.notes += "Conflicting positions exist; "
                return False
            
            # Check exchange connectivity
            if not await self._check_exchange_health():
                opportunity.notes += "Exchange connectivity issues; "
                return False
            
            # Check minimum position size
            if opportunity.recommended_size < self.risk_config.min_trade_amount:
                opportunity.notes += "Position size too small; "
                return False
            
            opportunity.status = OpportunityStatus.VALIDATED
            return True
            
        except Exception as e:
            logger.error(f"Error validating opportunity {opportunity.id}: {e}")
            opportunity.notes += f"Validation error: {e}; "
            return False
    
    async def _has_conflicting_positions(self, symbol: str) -> bool:
        """Check if there are conflicting positions for the symbol"""
        try:
            # Get current positions from both exchanges
            reya_positions = await self.reya_client.get_positions()
            hl_positions = await self.hyperliquid_client.get_positions()
            
            # Check for existing positions in the same symbol
            for pos in reya_positions + hl_positions:
                if pos.symbol == symbol and abs(pos.size) > 0:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking positions for {symbol}: {e}")
            return True  # Conservative: assume conflict if we can't check
    
    async def _check_exchange_health(self) -> bool:
        """Check if both exchanges are healthy"""
        try:
            reya_health = await self.reya_client.health_check()
            hl_health = await self.hyperliquid_client.health_check()
            
            return reya_health and hl_health
            
        except Exception as e:
            logger.error(f"Error checking exchange health: {e}")
            return False
    
    def _get_pair_config(self, symbol: str) -> Optional[TradingPair]:
        """Get trading pair configuration"""
        return next((pair for pair in self.trading_pairs if pair.symbol == symbol), None)
    
    async def cleanup_expired_opportunities(self) -> None:
        """Remove expired opportunities"""
        current_time = datetime.now(timezone.utc)
        expired_ids = []
        
        for opp_id, opportunity in self.opportunities.items():
            if opportunity.expires_at and current_time > opportunity.expires_at:
                opportunity.status = OpportunityStatus.EXPIRED
                expired_ids.append(opp_id)
                
                # Move to history
                self.opportunity_history.append(opportunity)
        
        # Remove expired opportunities
        for opp_id in expired_ids:
            del self.opportunities[opp_id]
        
        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired opportunities")
    
    def get_active_opportunities(self) -> List[ArbitrageOpportunity]:
        """Get all active opportunities"""
        return [
            opp for opp in self.opportunities.values()
            if opp.status in [OpportunityStatus.DETECTED, OpportunityStatus.VALIDATED]
        ]
    
    def get_opportunity_by_id(self, opportunity_id: str) -> Optional[ArbitrageOpportunity]:
        """Get opportunity by ID"""
        return self.opportunities.get(opportunity_id)
    
    def get_opportunities_for_symbol(self, symbol: str) -> List[ArbitrageOpportunity]:
        """Get all opportunities for a specific symbol"""
        return [opp for opp in self.opportunities.values() if opp.symbol == symbol]
    
    def get_best_opportunity(self) -> Optional[ArbitrageOpportunity]:
        """Get the best current opportunity based on risk/reward"""
        active_opportunities = self.get_active_opportunities()
        
        if not active_opportunities:
            return None
        
        # Sort by risk/reward ratio and confidence score
        best_opportunity = max(
            active_opportunities,
            key=lambda opp: opp.risk_reward_ratio * opp.confidence_score
        )
        
        return best_opportunity
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get detector statistics"""
        total_detected = len(self.opportunities) + len(self.opportunity_history)
        active_count = len(self.get_active_opportunities())
        
        # Calculate success rate from history
        executed_count = len([
            opp for opp in self.opportunity_history
            if opp.status == OpportunityStatus.EXECUTED
        ])
        
        success_rate = (executed_count / total_detected) if total_detected > 0 else 0.0
        
        return {
            "total_opportunities_detected": total_detected,
            "active_opportunities": active_count,
            "executed_opportunities": executed_count,
            "success_rate": success_rate,
            "average_confidence": sum(
                opp.confidence_score for opp in self.opportunities.values()
            ) / len(self.opportunities) if self.opportunities else 0.0
        }