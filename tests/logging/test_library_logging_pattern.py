"""Regression tests for the library logging pattern (NullHandler at import).

Importing ngraph must not install stream handlers or set levels: a bare
``import ngraph`` previously attached a StreamHandler(sys.stdout) to the
'ngraph' logger, duplicating records in host applications and corrupting
machine-readable stdout (``ngraph run --stdout``).
"""

import io
import logging
import subprocess
import sys

import pytest

from ngraph.logging import (
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


def test_import_attaches_only_null_handler():
    """A fresh `import ngraph` leaves only a NullHandler on the 'ngraph' logger."""
    code = (
        "import logging, ngraph; "
        "h = logging.getLogger('ngraph').handlers; "
        "assert len(h) == 1, h; "
        "assert type(h[0]) is logging.NullHandler, h"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_unconfigured_import_emits_nothing():
    """Without explicit setup, library log records produce no console output."""
    code = (
        "from ngraph.logging import get_logger; "
        "get_logger('ngraph.test').warning('sentinel-warning')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert "sentinel-warning" not in proc.stdout
    assert "sentinel-warning" not in proc.stderr


def test_no_duplicate_records_when_host_configures_root():
    """Host applications configuring the root logger see each record once."""
    stream = io.StringIO()
    root_handler = logging.StreamHandler(stream)
    logging.getLogger().addHandler(root_handler)
    try:
        get_logger("ngraph.dup_check").warning("dup-check-message")
    finally:
        logging.getLogger().removeHandler(root_handler)

    assert stream.getvalue().count("dup-check-message") == 1


def test_get_logger_does_not_install_stream_handlers():
    """get_logger() must not configure the root 'ngraph' logger."""
    get_logger("ngraph.some.module")

    root_logger = logging.getLogger("ngraph")
    assert all(isinstance(h, logging.NullHandler) for h in root_logger.handlers)
    # No level configured implicitly either
    assert root_logger.level == logging.NOTSET


def test_setup_root_logger_default_handler_uses_stderr():
    """The default console handler writes to stderr, keeping stdout clean."""
    setup_root_logger()

    handlers = logging.getLogger("ngraph").handlers
    assert len(handlers) == 1
    handler = handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stderr


def test_set_global_log_level_installs_console_handler():
    """set_global_log_level() configures the console handler (CLI entry path)."""
    set_global_log_level(logging.DEBUG)

    root_logger = logging.getLogger("ngraph")
    assert root_logger.level == logging.DEBUG
    non_null = [
        h for h in root_logger.handlers if not isinstance(h, logging.NullHandler)
    ]
    assert len(non_null) == 1


def test_records_propagate_for_caplog(caplog):
    """Records propagate to ancestor handlers (pytest caplog, host apps)."""
    with caplog.at_level(logging.INFO, logger="ngraph"):
        get_logger("ngraph.caplog_check").info("caplog-message")

    assert "caplog-message" in caplog.text
