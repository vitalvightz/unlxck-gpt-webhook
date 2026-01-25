"""Centralized utilities for preventing duplicate log messages."""

import logging
from typing import Any


class SingleWarningLogger:
    """Utility to log warnings only once per unique key.
    
    This prevents log spam when the same warning would be emitted multiple times
    during program execution.
    
    Example:
        logger = logging.getLogger(__name__)
        single_logger = SingleWarningLogger()
        
        # Will log the first time
        single_logger.warn_once("missing_system", "Unknown system: aerobic", logger)
        
        # Won't log again with the same key
        single_logger.warn_once("missing_system", "Unknown system: aerobic", logger)
    """
    
    def __init__(self):
        self._logged: set[tuple[str, ...]] = set()
    
    def warn_once(self, key: str, message: str, logger: logging.Logger) -> None:
        """Log a warning message only once per unique key.
        
        Args:
            key: Unique identifier for this warning type
            message: The warning message to log
            logger: The logger instance to use
        """
        key_tuple = (key,)
        if key_tuple not in self._logged:
            logger.warning(message)
            self._logged.add(key_tuple)
    
    def warn_once_keyed(self, key: tuple[str, ...], message: str, logger: logging.Logger) -> None:
        """Log a warning message only once per unique composite key.
        
        Args:
            key: Tuple of values forming a unique identifier
            message: The warning message to log
            logger: The logger instance to use
        """
        if key not in self._logged:
            logger.warning(message)
            self._logged.add(key)
    
    def has_logged(self, key: str | tuple[str, ...]) -> bool:
        """Check if a warning with this key has been logged.
        
        Args:
            key: The key to check
            
        Returns:
            True if a warning with this key has been logged
        """
        check_key = (key,) if isinstance(key, str) else key
        return check_key in self._logged
    
    def reset(self) -> None:
        """Clear all logged keys. Useful for testing."""
        self._logged.clear()
