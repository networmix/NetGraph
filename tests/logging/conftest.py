"""Own and restore logging state around application configuration tests."""

import logging

import pytest

import ngraph.logging as module


@pytest.fixture(autouse=True)
def isolated_logging(monkeypatch):
    logger = logging.getLogger("ngraph")
    handlers, level, propagate = logger.handlers[:], logger.level, logger.propagate
    monkeypatch.setattr(module, "_ROOT_LOGGER_CONFIGURED", False)
    logger.handlers = [logging.NullHandler()]
    logger.setLevel(logging.NOTSET)
    logger.propagate = True
    try:
        yield
    finally:
        for handler in logger.handlers:
            if handler not in handlers:
                handler.close()
        logger.handlers = handlers
        logger.setLevel(level)
        logger.propagate = propagate
