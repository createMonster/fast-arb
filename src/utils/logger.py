"""Logging utilities for Fast Arbitrage"""

import sys
from pathlib import Path
from loguru import logger
from typing import Optional


def setup_logger(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    rotation: str = "1 day",
    retention: str = "7 days",
    format_string: Optional[str] = None
) -> None:
    """Setup logger configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        rotation: Log rotation policy
        retention: Log retention policy
        format_string: Custom format string
    """
    
    # Remove default logger
    logger.remove()
    
    # Default format
    if format_string is None:
        format_string = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
    
    # Console handler
    logger.add(
        sys.stdout,
        format=format_string,
        level=log_level,
        colorize=True,
        backtrace=True,
        diagnose=True
    )
    
    # File handler (if specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.add(
            log_file,
            format=format_string,
            level=log_level,
            rotation=rotation,
            retention=retention,
            compression="zip",
            backtrace=True,
            diagnose=True
        )
    
    logger.info(f"Logger initialized with level: {log_level}")
    if log_file:
        logger.info(f"Logging to file: {log_file}")


def get_logger(name: str):
    """Get a logger instance with the given name
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Logger instance
    """
    return logger.bind(name=name)


class LoggerMixin:
    """Mixin class to add logging capabilities to any class"""
    
    @property
    def logger(self):
        """Get logger instance for this class"""
        return logger.bind(name=self.__class__.__name__)