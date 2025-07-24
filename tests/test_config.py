"""Tests for configuration management"""

import pytest
import tempfile
import os
from pathlib import Path

from src.config.config_manager import ConfigManager, ArbitrageConfig


class TestConfigManager:
    """Test configuration manager"""
    
    def test_load_valid_config(self):
        """Test loading valid configuration"""
        config_content = """
general:
  log_level: "INFO"
  update_interval: 5
  simulation_mode: true

reya:
  rpc_url: "https://rpc.reya.network"
  ws_url: "wss://ws.reya.network"
  private_key: "test_key"

hyperliquid:
  testnet: true
  private_key: "test_key"

arbitrage:
  min_spread_threshold: 0.1
  max_spread_threshold: 2.0
  check_interval: 10

risk_management:
  max_total_position: 10000
  max_position_per_pair: 5000
  min_trade_amount: 100
  stop_loss_percentage: 5.0
  take_profit_percentage: 2.0

trading_pairs:
  SOL-USD:
    reya_symbol: "SOL-USD"
    hyperliquid_symbol: "SOL"
    min_funding_rate_diff: 0.05
    max_position_size: 1000
  ETH-USD:
    reya_symbol: "ETH-USD"
    hyperliquid_symbol: "ETH"
    min_funding_rate_diff: 0.05
    max_position_size: 2000
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name
        
        try:
            config_manager = ConfigManager(config_path)
            
            general_config = config_manager.get_general_config()
            reya_config = config_manager.get_reya_config()
            arbitrage_config = config_manager.get_arbitrage_config()
            trading_pairs = config_manager.get_trading_pairs()
            
            assert general_config.log_level == "INFO"
            assert general_config.simulation_mode is True
            assert reya_config.rpc_url == "https://rpc.reya.network"
            assert arbitrage_config.min_spread_threshold == 0.1
            assert len(trading_pairs) == 2
            assert any(pair.symbol == "SOL-USD" for pair in trading_pairs)
            
        finally:
            os.unlink(config_path)
    
    def test_missing_config_file(self):
        """Test handling of missing config file"""
        with pytest.raises(FileNotFoundError):
            ConfigManager("nonexistent.yaml")
    
    def test_invalid_yaml(self):
        """Test handling of invalid YAML"""
        invalid_content = """
general:
  log_level: "INFO"
  invalid_yaml: [
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(invalid_content)
            config_path = f.name
        
        try:
            with pytest.raises(Exception):
                ConfigManager(config_path)
        finally:
            os.unlink(config_path)
    
    def test_environment_variable_override(self):
        """Test environment variable override"""
        config_content = """
general:
  log_level: "INFO"
  simulation_mode: true

reya:
  rpc_url: "https://rpc.reya.network"
  private_key: "${REYA_PRIVATE_KEY}"
"""
        
        # Set environment variable
        os.environ["REYA_PRIVATE_KEY"] = "env_test_key"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name
        
        try:
            config_manager = ConfigManager(config_path)
            reya_config = config_manager.get_reya_config()
            
            assert reya_config.private_key == "env_test_key"
            
        finally:
            os.unlink(config_path)
            if "REYA_PRIVATE_KEY" in os.environ:
                del os.environ["REYA_PRIVATE_KEY"]
    
    def test_get_trading_pair_config(self):
        """Test getting trading pair configuration"""
        config_content = """
trading_pairs:
  SOL-USD:
    reya_symbol: "SOL-USD"
    hyperliquid_symbol: "SOL"
    min_funding_rate_diff: 0.05
    max_position_size: 1000
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name
        
        try:
            config_manager = ConfigManager(config_path)
            
            pair_config = config_manager.get_trading_pair_config("SOL-USD")
            assert pair_config is not None
            assert pair_config.reya_symbol == "SOL-USD"
            assert pair_config.hyperliquid_symbol == "SOL"
            
            # Test non-existent pair
            pair_config = config_manager.get_trading_pair_config("BTC-USD")
            assert pair_config is None
            
        finally:
            os.unlink(config_path)