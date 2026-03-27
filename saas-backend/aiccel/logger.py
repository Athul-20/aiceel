# aiccel/logger.py
"""
AICCEL Logging Module
=====================

Unified logging for the AICCEL framework.
This module provides a single entry point for all logging functionality.

Usage:
    from aiccel.logger import AILogger, get_logger, configure_logging

    # Quick logger for a module
    logger = get_logger("my_module")
    logger.info("Hello!")

    # Full-featured agent logger
    logger = AILogger("agent", verbose=True)
    trace_id = logger.trace_start("process_query", {"query": "..."})
    logger.trace_step(trace_id, "step_1")
    logger.trace_end(trace_id, {"result": "..."})
"""

# Re-export from logging_config for unified interface
from .logging_config import (
    # Main logger class
    AgentLogger as AILogger,
)
from .logging_config import (
    # Formatters
    CleanFormatter,
    # Colors
    Colors,
    # Spinner utilities
    Spinner,
    StructuredFormatter,
    configure_logging,
    # Factory functions
    get_logger,
    spinner,
    status,
)


__all__ = [
    # Main exports
    'AILogger',
    # Formatters (for advanced use)
    'CleanFormatter',
    'Colors',
    # Utilities
    'Spinner',
    'StructuredFormatter',
    'configure_logging',
    'get_logger',
    'spinner',
    'status',
]


# Factory function for compatibility with existing code
def create_logger(name: str, **kwargs) -> AILogger:
    """
    Factory function to create an AILogger instance.

    Args:
        name: Logger name
        **kwargs: Additional options (verbose, level, log_file)

    Returns:
        AILogger instance
    """
    verbose = kwargs.get("verbose", False)
    log_file = kwargs.get("log_file")
    structured_logging = kwargs.get("structured_logging", False)
    return AILogger(name=name, verbose=verbose, log_file=log_file, structured_logging=structured_logging)
