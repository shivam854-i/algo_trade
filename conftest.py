"""Pytest Global Configuration and Disabled Market Test Gating.

By default, any test marked with `@pytest.mark.disabled_market` is skipped unless
the test runner explicitly requests it using `-m disabled_market`.
"""

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "disabled_market: marks tests as testing disabled markets (skipped by default unless -m disabled_market is specified)",
    )


def pytest_collection_modifyitems(config, items):
    marker_expr = config.getoption("-m", default="")
    # If the user explicitly requested disabled_market, do not skip
    if "disabled_market" in marker_expr:
        return

    skip_disabled = pytest.mark.skip(
        reason="Market is disabled by default (NSE-only focus). Run with '-m disabled_market' to execute."
    )
    for item in items:
        if "disabled_market" in item.keywords:
            item.add_marker(skip_disabled)
