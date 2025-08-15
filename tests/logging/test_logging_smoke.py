from __future__ import annotations

import logging

from ngraph.logging import get_logger, set_global_log_level


def test_set_global_log_level_and_get_logger_smoke(caplog) -> None:
    # Switch to WARNING then DEBUG and verify effective level changes
    set_global_log_level(logging.WARNING)
    lg = get_logger("ngraph.smoke")
    assert lg.isEnabledFor(logging.WARNING)

    caplog.set_level(logging.DEBUG, logger="ngraph.smoke")
    lg.debug("debug message")
    assert any(
        r.levelno == logging.DEBUG and r.name == "ngraph.smoke" for r in caplog.records
    )
