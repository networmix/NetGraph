"""Centralized logging configuration for NetGraph.

Follows the standard library pattern: importing the package attaches only a
``logging.NullHandler`` to the root ``ngraph`` logger and never installs
stream handlers or sets levels. Applications opt into console output by
calling ``setup_root_logger()`` explicitly, or implicitly via
``set_global_log_level()``. The CLI does both in ``main()``: it calls
``setup_root_logger()`` first, then sets the level from
``--verbose``/``--quiet``.
"""

import logging
import sys
from typing import Optional

# Flag to track if we've already set up the root logger
_ROOT_LOGGER_CONFIGURED = False


def setup_root_logger(
    level: int = logging.INFO,
    format_string: Optional[str] = None,
    handler: Optional[logging.Handler] = None,
) -> None:
    """Set up the root NetGraph logger with a single handler.

    Subsequent calls are no-ops until ``reset_logging()`` is called.

    Args:
        level: Logging level (default: INFO).
        format_string: Custom format string (optional).
        handler: Custom handler (optional, defaults to StreamHandler(sys.stderr)).
    """
    global _ROOT_LOGGER_CONFIGURED

    if _ROOT_LOGGER_CONFIGURED:
        return

    root_logger = logging.getLogger("ngraph")
    root_logger.setLevel(level)

    # Replace the import-time NullHandler (and any stale handlers)
    root_logger.handlers.clear()

    # Default format with timestamps, level, logger name, and message
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Default to stderr so machine-readable stdout (e.g. `ngraph run --stdout`)
    # stays free of log lines.
    if handler is None:
        handler = logging.StreamHandler(sys.stderr)

    formatter = logging.Formatter(format_string)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Let logs propagate to the root logger so host applications and pytest
    # can capture them
    root_logger.propagate = True

    _ROOT_LOGGER_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Get a logger under NetGraph's logging hierarchy.

    Use this everywhere in the package. It configures nothing: handlers and
    levels are inherited from the root 'ngraph' logger, which is configured
    only when an application calls setup_root_logger() (directly or via
    set_global_log_level()).

    Args:
        name: Logger name (typically __name__ from calling module).

    Returns:
        Logger instance inheriting from the root ngraph logger.
    """
    logger = logging.getLogger(name)

    # Don't add handlers to child loggers - they inherit from root
    logger.setLevel(logging.NOTSET)  # Inherit from parent

    return logger


def set_global_log_level(level: int) -> None:
    """Set the log level for all NetGraph loggers.

    Installs the default console handler via setup_root_logger() if logging
    has not been configured yet. Intended for applications (e.g. the CLI);
    library code never calls this implicitly.

    Args:
        level: Logging level (e.g., logging.DEBUG, logging.INFO).
    """
    # Ensure a console handler exists for applications that only call this
    setup_root_logger(level=level)

    # Set the root level for all ngraph loggers
    root_logger = logging.getLogger("ngraph")
    root_logger.setLevel(level)

    # Also update handlers to respect the new level
    for handler in root_logger.handlers:
        handler.setLevel(level)


def enable_debug_logging() -> None:
    """Enable debug logging for the entire package."""
    set_global_log_level(logging.DEBUG)


def disable_debug_logging() -> None:
    """Disable debug logging, set to INFO level."""
    set_global_log_level(logging.INFO)


def reset_logging() -> None:
    """Reset logging configuration (mainly for testing)."""
    global _ROOT_LOGGER_CONFIGURED
    _ROOT_LOGGER_CONFIGURED = False

    # Restore the unconfigured import-time state: only a NullHandler attached
    root_logger = logging.getLogger("ngraph")
    root_logger.handlers.clear()
    root_logger.setLevel(logging.NOTSET)
    root_logger.addHandler(logging.NullHandler())


# Library pattern: attach only a NullHandler at import time so unconfigured
# use emits nothing (and avoids the logging.lastResort fallback) while records
# still propagate to handlers configured by the host application.
logging.getLogger("ngraph").addHandler(logging.NullHandler())
