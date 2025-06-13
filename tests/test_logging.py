"""Test the centralized logging functionality."""

import logging
from io import StringIO

from ngraph.logging import enable_debug_logging, get_logger, set_global_log_level


def test_centralized_logging():
    """Test that centralized logging works properly."""
    # Create a logger
    logger = get_logger("ngraph.test")

    # Capture log output
    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.DEBUG)

    # Remove any existing handlers and add our test handler
    logger.handlers.clear()
    logger.addHandler(handler)

    # Test info level (should appear by default)
    logger.info("Test info message")
    log_output = log_capture.getvalue()
    assert "Test info message" in log_output

    # Test debug level (should not appear by default)
    log_capture.seek(0)
    log_capture.truncate(0)
    logger.debug("Test debug message")
    log_output = log_capture.getvalue()
    assert "Test debug message" not in log_output

    # Enable debug logging and test again
    enable_debug_logging()
    logger.debug("Test debug message after enable")
    log_output = log_capture.getvalue()
    assert "Test debug message after enable" in log_output


def test_logger_naming():
    """Test that loggers use consistent naming."""
    logger = get_logger("ngraph.workflow.test")
    assert logger.name == "ngraph.workflow.test"


def test_multiple_loggers():
    """Test that multiple loggers can be created and configured."""
    logger1 = get_logger("ngraph.module1")
    logger2 = get_logger("ngraph.module2")

    assert logger1.name == "ngraph.module1"
    assert logger2.name == "ngraph.module2"
    assert logger1 is not logger2

    # Setting global level should affect the root logger
    set_global_log_level(logging.WARNING)
    root_logger = logging.getLogger("ngraph")
    assert root_logger.level == logging.WARNING

    # Child loggers inherit from root (effective level)
    assert logger1.getEffectiveLevel() == logging.WARNING
    assert logger2.getEffectiveLevel() == logging.WARNING
