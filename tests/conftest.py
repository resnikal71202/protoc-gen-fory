from __future__ import annotations

import pytest

import helpers


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if helpers.buf_available():
        return
    skip = pytest.mark.skip(reason="buf CLI not on PATH")
    for item in items:
        if "needs_buf" in item.keywords:
            item.add_marker(skip)
