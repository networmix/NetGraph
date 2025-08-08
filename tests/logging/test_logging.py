"""Tests for centralized logging behavior and configuration."""

import logging
from io import StringIO

import pytest

from ngraph.logging import (
    disable_debug_logging,
    enable_debug_logging,
    get_logger,
    reset_logging,
    set_global_log_level,
    setup_root_logger,
)


@pytest.fixture(autouse=True)
def _reset_logging_each_test():
    """Reset logging state before and after each test to avoid cross-test bleed."""
    reset_logging()
    yield
    reset_logging()


def test_effective_levels_enable_disable():
    """Verify effective levels: INFO by default, DEBUG after enable, back to INFO after disable."""
    logger = get_logger("ngraph.test")

    capture = StringIO()
    handler = logging.StreamHandler(capture)
    handler.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.addHandler(handler)

    # INFO should be emitted by default
    logger.info("info-1")
    assert "info-1" in capture.getvalue()

    # DEBUG should not be emitted by default (effective level INFO)
    capture.seek(0)
    capture.truncate(0)
    logger.debug("debug-1")
    assert "debug-1" not in capture.getvalue()

    # After enabling debug, DEBUG should pass
    enable_debug_logging()
    logger.debug("debug-2")
    assert "debug-2" in capture.getvalue()

    # After disabling debug, DEBUG should be filtered again
    capture.seek(0)
    capture.truncate(0)
    disable_debug_logging()
    logger.debug("debug-3")
    assert "debug-3" not in capture.getvalue()


def test_global_level_propagates_to_children_and_new_loggers():
    """Changing global level updates effective level of existing and new child loggers."""
    logger1 = get_logger("ngraph.module1")
    logger2 = get_logger("ngraph.module2")

    # Default effective level is INFO
    assert logger1.getEffectiveLevel() == logging.INFO
    assert logger2.getEffectiveLevel() == logging.INFO

    set_global_log_level(logging.WARNING)
    assert logger1.getEffectiveLevel() == logging.WARNING
    assert logger2.getEffectiveLevel() == logging.WARNING

    # New child loggers should also inherit updated level
    logger3 = get_logger("ngraph.module3")
    assert logger3.getEffectiveLevel() == logging.WARNING


def test_setup_root_logger_idempotent_no_duplicate_handlers():
    """Repeated setup should not accumulate handlers or change semantics."""
    # Start clean and add a known handler
    capture = StringIO()
    handler = logging.StreamHandler(capture)
    setup_root_logger(level=logging.INFO, handler=handler)

    root_logger = logging.getLogger("ngraph")
    assert len(root_logger.handlers) == 1

    # Calling setup again must not add handlers
    setup_root_logger(level=logging.DEBUG)
    assert len(root_logger.handlers) == 1

    # And changing level via setup should not override explicit global level API
    set_global_log_level(logging.ERROR)
    assert root_logger.level == logging.ERROR


def test_custom_format_string_applied():
    """Custom format string is respected by the root handler."""
    # Ensure clean state, then install a custom format and handler
    capture = StringIO()
    handler = logging.StreamHandler(capture)
    fmt = "LEVEL:%(levelname)s|NAME:%(name)s|MSG:%(message)s"
    setup_root_logger(level=logging.INFO, format_string=fmt, handler=handler)

    logger = get_logger("ngraph.test.format")
    logger.info("hello")
    out = capture.getvalue()
    assert "LEVEL:INFO" in out
    assert "NAME:ngraph.test.format" in out
    assert "MSG:hello" in out
