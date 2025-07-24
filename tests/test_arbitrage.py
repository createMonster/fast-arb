"""Tests for arbitrage components"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone, timedelta

from src.arbitrage.funding_monitor import FundingRateMonitor, FundingRateData, FundingRateSpread
from src.arbitrage.opportunity_detector import OpportunityDetector, ArbitrageOpportunity, OpportunityType, OpportunityStatus
from src.arbitrage.trade_executor import TradeExecutor, TradeExecution, ExecutionStatus
from src.exchanges.base_exchange import MarketData, Order, OrderSide, OrderType, OrderStatus
from src.config.config_manager import RiskManagementConfig


class TestFundingRateMonitor:
    """Test funding rate monitor"""
    
    @pytest.fixture
    def mock_exchanges(self):
        """Create mock exchange clients"""
        reya_client = Mock()
        reya_client.get_funding_rate = AsyncMock()
        reya_client.get_market_data = AsyncMock()
        
        hl_client = Mock()
        hl_client.get_funding_rate = AsyncMock()
        hl_client.get_market_data = AsyncMock()
        
        return reya_client, hl_client
    
    @pytest.fixture
    def funding_monitor(self, mock_exchanges):
        """Create funding rate monitor instance"""
        reya_client, hl_client = mock_exchanges
        return FundingRateMonitor(
            reya_client=reya_client,
            hyperliquid_client=hl_client,
            symbols=["BTC-USD", "ETH-USD"],
            update_interval=5
        )
    
    @pytest.mark.asyncio
    async def test_update_funding_rates(self, funding_monitor, mock_exchanges):
        """Test funding rate updates"""
        reya_client, hl_client = mock_exchanges
        
        # Mock funding rate responses
        reya_client.get_funding_rate.return_value = 0.01  # 1%
        hl_client.get_funding_rate.return_value = -0.005  # -0.5%
        
        # Mock market data
        market_data = MarketData(
            symbol="BTC-USD",
            price=50000.0,
            bid=49990.0,
            ask=50010.0,
            volume=1000.0,
            timestamp=datetime.now(timezone.utc)
        )
        reya_client.get_market_data.return_value = market_data
        hl_client.get_market_data.return_value = market_data
        
        # Update funding rates
        await funding_monitor._update_funding_rates()
        
        # Check that data was stored
        assert "BTC-USD" in funding_monitor.funding_rates
        btc_data = funding_monitor.funding_rates["BTC-USD"]
        
        assert btc_data.reya_rate == 0.01
        assert btc_data.hyperliquid_rate == -0.005
        assert btc_data.price == 50000.0
    
    @pytest.mark.asyncio
    async def test_calculate_spread(self, funding_monitor):
        """Test spread calculation"""
        # Set up funding rate data
        funding_monitor.funding_rates["BTC-USD"] = FundingRateData(
            symbol="BTC-USD",
            reya_rate=0.01,
            hyperliquid_rate=-0.005,
            price=50000.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Calculate spread
        spread = funding_monitor._calculate_spread("BTC-USD")
        
        assert spread is not None
        assert spread.symbol == "BTC-USD"
        assert spread.reya_rate == 0.01
        assert spread.hyperliquid_rate == -0.005
        assert spread.spread_percentage == 1.5  # 1% - (-0.5%) = 1.5%
    
    def test_get_current_spreads(self, funding_monitor):
        """Test getting current spreads"""
        # Set up test data
        now = datetime.now(timezone.utc)
        
        funding_monitor.current_spreads["BTC-USD"] = FundingRateSpread(
            symbol="BTC-USD",
            reya_rate=0.01,
            hyperliquid_rate=-0.005,
            spread_percentage=1.5,
            price=50000.0,
            timestamp=now
        )
        
        spreads = funding_monitor.get_current_spreads()
        
        assert len(spreads) == 1
        assert "BTC-USD" in spreads
        assert spreads["BTC-USD"].spread_percentage == 1.5


class TestOpportunityDetector:
    """Test opportunity detector"""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock configuration"""
        config = Mock()
        config.arbitrage.min_spread_threshold = 0.1
        config.arbitrage.max_spread_threshold = 2.0
        config.risk_management.max_position_per_pair = 5000
        config.risk_management.min_trade_amount = 100
        
        # Mock trading pairs
        btc_pair = Mock()
        btc_pair.min_funding_rate_diff = 0.05
        btc_pair.max_position_size = 1000
        
        config.trading_pairs = {"BTC-USD": btc_pair}
        
        return config
    
    @pytest.fixture
    def mock_funding_monitor(self):
        """Create mock funding monitor"""
        monitor = Mock()
        monitor.get_current_spreads = Mock()
        return monitor
    
    @pytest.fixture
    def opportunity_detector(self, mock_config, mock_funding_monitor):
        """Create opportunity detector instance"""
        return OpportunityDetector(
            config=mock_config,
            funding_monitor=mock_funding_monitor
        )
    
    @pytest.mark.asyncio
    async def test_analyze_spread_profitable(self, opportunity_detector, mock_funding_monitor):
        """Test analyzing profitable spread"""
        # Create a profitable spread
        spread = FundingRateSpread(
            symbol="BTC-USD",
            reya_rate=0.01,
            hyperliquid_rate=-0.005,
            spread_percentage=1.5,  # 1.5% spread
            price=50000.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Analyze the spread
        opportunity = await opportunity_detector.analyze_spread(spread)
        
        assert opportunity is not None
        assert opportunity.symbol == "BTC-USD"
        assert opportunity.opportunity_type == OpportunityType.FUNDING_RATE
        assert opportunity.expected_profit > 0
        assert opportunity.reya_action == "long"
        assert opportunity.hyperliquid_action == "short"
    
    @pytest.mark.asyncio
    async def test_analyze_spread_unprofitable(self, opportunity_detector, mock_funding_monitor):
        """Test analyzing unprofitable spread"""
        # Create an unprofitable spread (below threshold)
        spread = FundingRateSpread(
            symbol="BTC-USD",
            reya_rate=0.001,
            hyperliquid_rate=-0.001,
            spread_percentage=0.02,  # 0.02% spread (below 0.1% threshold)
            price=50000.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Analyze the spread
        opportunity = await opportunity_detector.analyze_spread(spread)
        
        assert opportunity is None
    
    def test_calculate_position_size(self, opportunity_detector):
        """Test position size calculation"""
        spread = FundingRateSpread(
            symbol="BTC-USD",
            reya_rate=0.01,
            hyperliquid_rate=-0.005,
            spread_percentage=1.5,
            price=50000.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        position_size = opportunity_detector._calculate_position_size(spread)
        
        assert position_size > 0
        assert position_size <= 1000  # Max position size from config
    
    def test_estimate_profit_loss(self, opportunity_detector):
        """Test profit/loss estimation"""
        spread = FundingRateSpread(
            symbol="BTC-USD",
            reya_rate=0.01,
            hyperliquid_rate=-0.005,
            spread_percentage=1.5,
            price=50000.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        position_size = 0.1  # 0.1 BTC
        
        profit, loss = opportunity_detector._estimate_profit_loss(spread, position_size)
        
        assert profit > 0
        assert loss > 0
        assert profit > loss  # Should be profitable


class TestTradeExecutor:
    """Test trade executor"""
    
    @pytest.fixture
    def mock_exchanges(self):
        """Create mock exchange clients"""
        reya_client = Mock()
        reya_client.health_check = AsyncMock(return_value=True)
        reya_client.get_balance = AsyncMock()
        reya_client.place_order = AsyncMock()
        reya_client.get_order_status = AsyncMock()
        reya_client.cancel_order = AsyncMock()
        
        hl_client = Mock()
        hl_client.health_check = AsyncMock(return_value=True)
        hl_client.get_balance = AsyncMock()
        hl_client.place_order = AsyncMock()
        hl_client.get_order_status = AsyncMock()
        hl_client.cancel_order = AsyncMock()
        
        return reya_client, hl_client
    
    @pytest.fixture
    def mock_risk_config(self):
        """Create mock risk configuration"""
        return RiskManagementConfig(
            max_total_position=10000,
            max_position_per_pair=5000,
            min_trade_amount=100,
            stop_loss_percentage=5.0,
            take_profit_percentage=2.0
        )
    
    @pytest.fixture
    def trade_executor(self, mock_exchanges, mock_risk_config):
        """Create trade executor instance"""
        reya_client, hl_client = mock_exchanges
        return TradeExecutor(
            reya_client=reya_client,
            hyperliquid_client=hl_client,
            risk_config=mock_risk_config,
            dry_run=True
        )
    
    @pytest.fixture
    def mock_opportunity(self):
        """Create mock arbitrage opportunity"""
        return ArbitrageOpportunity(
            id="test_opp_1",
            symbol="BTC-USD",
            opportunity_type=OpportunityType.FUNDING_RATE,
            status=OpportunityStatus.VALIDATED,
            reya_action="long",
            hyperliquid_action="short",
            recommended_size=0.1,
            expected_profit=100.0,
            max_loss=20.0,
            risk_reward_ratio=5.0,
            confidence=0.85,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)
        )
    
    @pytest.mark.asyncio
    async def test_simulate_execution(self, trade_executor, mock_opportunity, mock_exchanges):
        """Test simulated execution (dry run)"""
        reya_client, hl_client = mock_exchanges
        
        # Mock balance check
        from src.exchanges.base_exchange import Balance
        reya_client.get_balance.return_value = [
            Balance(currency="USD", total=10000, available=8000, locked=2000)
        ]
        hl_client.get_balance.return_value = [
            Balance(currency="USD", total=10000, available=8000, locked=2000)
        ]
        
        # Execute opportunity
        execution = await trade_executor.execute_opportunity(mock_opportunity)
        
        assert execution is not None
        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.symbol == "BTC-USD"
        assert execution.planned_size == 0.1
        assert execution.executed_size == 0.1
        assert execution.realized_pnl > 0  # Should be profitable in simulation
    
    @pytest.mark.asyncio
    async def test_pre_execution_validation_expired(self, trade_executor, mock_opportunity):
        """Test pre-execution validation with expired opportunity"""
        # Make opportunity expired
        mock_opportunity.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        
        # Should fail validation
        is_valid = await trade_executor._pre_execution_validation(mock_opportunity)
        assert is_valid is False
        assert mock_opportunity.status == OpportunityStatus.EXPIRED
    
    @pytest.mark.asyncio
    async def test_insufficient_balance(self, trade_executor, mock_opportunity, mock_exchanges):
        """Test execution with insufficient balance"""
        reya_client, hl_client = mock_exchanges
        
        # Mock insufficient balance
        from src.exchanges.base_exchange import Balance
        reya_client.get_balance.return_value = [
            Balance(currency="USD", total=10, available=5, locked=5)  # Very low balance
        ]
        hl_client.get_balance.return_value = [
            Balance(currency="USD", total=10, available=5, locked=5)
        ]
        
        # Should fail validation
        is_valid = await trade_executor._pre_execution_validation(mock_opportunity)
        assert is_valid is False
    
    def test_get_execution_statistics(self, trade_executor):
        """Test execution statistics"""
        # Add some mock executions
        execution1 = TradeExecution(
            id="exec_1",
            opportunity_id="opp_1",
            symbol="BTC-USD",
            status=ExecutionStatus.COMPLETED,
            reya_order=None,
            hyperliquid_order=None,
            planned_size=0.1,
            executed_size=0.1,
            average_entry_price_reya=50000.0,
            average_entry_price_hl=50000.0,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            realized_pnl=100.0,
            execution_cost=5.0,
            slippage=0.001
        )
        
        execution2 = TradeExecution(
            id="exec_2",
            opportunity_id="opp_2",
            symbol="ETH-USD",
            status=ExecutionStatus.FAILED,
            reya_order=None,
            hyperliquid_order=None,
            planned_size=1.0,
            executed_size=0.0,
            average_entry_price_reya=0.0,
            average_entry_price_hl=0.0,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            realized_pnl=-10.0,
            execution_cost=2.0,
            slippage=0.0
        )
        
        trade_executor.executions["exec_1"] = execution1
        trade_executor.executions["exec_2"] = execution2
        
        stats = trade_executor.get_execution_statistics()
        
        assert stats["total_executions"] == 2
        assert stats["completed_executions"] == 1
        assert stats["success_rate"] == 0.5
        assert stats["total_pnl"] == 90.0  # 100 - 10
        assert stats["total_cost"] == 7.0   # 5 + 2
        assert stats["net_pnl"] == 83.0     # 90 - 7


class TestIntegration:
    """Integration tests for arbitrage components"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_flow(self):
        """Test end-to-end arbitrage flow"""
        # This would test the complete flow from funding rate monitoring
        # to opportunity detection to trade execution
        # For now, we'll just ensure components can be instantiated together
        
        # Mock exchanges
        reya_client = Mock()
        hl_client = Mock()
        
        # Create funding monitor
        funding_monitor = FundingRateMonitor(
            reya_client=reya_client,
            hyperliquid_client=hl_client,
            symbols=["BTC-USD"],
            update_interval=5
        )
        
        # Mock config
        config = Mock()
        config.arbitrage.min_spread_threshold = 0.1
        config.trading_pairs = {}
        
        # Create opportunity detector
        opportunity_detector = OpportunityDetector(
            config=config,
            funding_monitor=funding_monitor
        )
        
        # Mock risk config
        risk_config = RiskManagementConfig(
            max_total_position=10000,
            max_position_per_pair=5000,
            min_trade_amount=100,
            stop_loss_percentage=5.0,
            take_profit_percentage=2.0
        )
        
        # Create trade executor
        trade_executor = TradeExecutor(
            reya_client=reya_client,
            hyperliquid_client=hl_client,
            risk_config=risk_config,
            dry_run=True
        )
        
        # Verify all components are created successfully
        assert funding_monitor is not None
        assert opportunity_detector is not None
        assert trade_executor is not None