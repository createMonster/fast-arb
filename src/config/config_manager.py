"""Configuration Manager for Fast Arbitrage"""

import os
import yaml
from typing import Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator
from loguru import logger


class ExchangeConfig(BaseModel):
    """Exchange configuration model"""
    enabled: bool = True
    private_key: str = ""
    

class ReyaConfig(ExchangeConfig):
    """Reya Network configuration"""
    websocket_url: str = "wss://ws.reya.network"
    rpc_url: str = "https://rpc.reya.network"
    chain_id: int = 1729
    account_id: str = ""


class HyperliquidConfig(ExchangeConfig):
    """Hyperliquid configuration"""
    api_url: str = "https://api.hyperliquid.xyz"
    testnet: bool = False


class TradingPair(BaseModel):
    """Trading pair configuration"""
    symbol: str
    reya_symbol: str
    hyperliquid_symbol: str
    enabled: bool = True
    min_funding_rate_diff: float = 0.3
    max_position: float = 1000.0


class ArbitrageConfig(BaseModel):
    """Arbitrage strategy configuration"""
    funding_rate: Dict[str, float] = Field(default_factory=lambda: {
        "min_spread_threshold": 0.5,
        "max_spread_threshold": 10.0,
        "check_interval": 60
    })


class RiskManagementConfig(BaseModel):
    """Risk management configuration"""
    max_total_position: float = 10000.0
    max_position_per_pair: float = 2000.0
    min_trade_amount: float = 100.0
    stop_loss_percentage: float = 2.0
    take_profit_percentage: float = 1.0


class GeneralConfig(BaseModel):
    """General application configuration"""
    log_level: str = "INFO"
    update_interval: int = 30
    dry_run: bool = True


class ConfigManager:
    """Configuration manager for the arbitrage system"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config/config.yaml"
        self.config: Dict[str, Any] = {}
        self._load_environment()
        self._load_config()
        
    def _load_environment(self):
        """Load environment variables from .env file"""
        env_path = Path(".env")
        if env_path.exists():
            load_dotenv(env_path)
            logger.info("Loaded environment variables from .env file")
        else:
            logger.warning(".env file not found, using system environment variables")
    
    def _load_config(self):
        """Load configuration from YAML file"""
        config_file = Path(self.config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from {self.config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML configuration: {e}")
    
    def get_general_config(self) -> GeneralConfig:
        """Get general configuration"""
        return GeneralConfig(**self.config.get('general', {}))
    
    def get_reya_config(self) -> ReyaConfig:
        """Get Reya Network configuration with environment variables"""
        reya_config = self.config.get('exchanges', {}).get('reya', {})
        
        # Override with environment variables
        reya_config['private_key'] = os.getenv('REYA_PRIVATE_KEY', reya_config.get('private_key', ''))
        reya_config['account_id'] = os.getenv('REYA_ACCOUNT_ID', reya_config.get('account_id', ''))
        reya_config['chain_id'] = int(os.getenv('REYA_CHAIN_ID', reya_config.get('chain_id', 1729)))
        reya_config['rpc_url'] = os.getenv('REYA_RPC_URL', reya_config.get('rpc_url', 'https://rpc.reya.network'))
        reya_config['websocket_url'] = os.getenv('REYA_WS_URL', reya_config.get('websocket_url', 'wss://ws.reya.network'))
        
        return ReyaConfig(**reya_config)
    
    def get_hyperliquid_config(self) -> HyperliquidConfig:
        """Get Hyperliquid configuration with environment variables"""
        hl_config = self.config.get('exchanges', {}).get('hyperliquid', {})
        
        # Override with environment variables
        hl_config['private_key'] = os.getenv('HYPERLIQUID_PRIVATE_KEY', hl_config.get('private_key', ''))
        hl_config['api_url'] = os.getenv('HYPERLIQUID_API_URL', hl_config.get('api_url', 'https://api.hyperliquid.xyz'))
        hl_config['testnet'] = os.getenv('HYPERLIQUID_TESTNET', str(hl_config.get('testnet', False))).lower() == 'true'
        
        return HyperliquidConfig(**hl_config)
    
    def get_trading_pairs(self) -> list[TradingPair]:
        """Get list of trading pairs"""
        pairs_config = self.config.get('trading_pairs', [])
        return [TradingPair(**pair) for pair in pairs_config]
    
    def get_arbitrage_config(self) -> ArbitrageConfig:
        """Get arbitrage strategy configuration"""
        return ArbitrageConfig(**self.config.get('arbitrage', {}))
    
    def get_risk_management_config(self) -> RiskManagementConfig:
        """Get risk management configuration"""
        return RiskManagementConfig(**self.config.get('risk_management', {}))
    
    def is_dry_run(self) -> bool:
        """Check if running in dry run mode"""
        return os.getenv('DRY_RUN', str(self.get_general_config().dry_run)).lower() == 'true'
    
    def get_log_level(self) -> str:
        """Get log level"""
        return os.getenv('LOG_LEVEL', self.get_general_config().log_level)
    
    def validate_config(self) -> bool:
        """Validate the configuration"""
        try:
            # Validate all configurations
            self.get_general_config()
            reya_config = self.get_reya_config()
            hl_config = self.get_hyperliquid_config()
            self.get_trading_pairs()
            self.get_arbitrage_config()
            self.get_risk_management_config()
            
            # Check required fields
            if not reya_config.private_key and not self.is_dry_run():
                logger.error("Reya private key is required for live trading")
                return False
            
            if not hl_config.private_key and not self.is_dry_run():
                logger.error("Hyperliquid private key is required for live trading")
                return False
            
            if not reya_config.account_id and not self.is_dry_run():
                logger.error("Reya account ID is required for live trading")
                return False
            
            logger.info("Configuration validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            return False