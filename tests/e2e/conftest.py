from __future__ import annotations

import os

import pytest


@pytest.fixture
def pair() -> tuple[str, str]:
    """(writer, reader) for roundtrip tests, from FORY_RT_WRITER / FORY_RT_READER."""
    writer = os.environ.get("FORY_RT_WRITER")
    reader = os.environ.get("FORY_RT_READER")
    if not writer or not reader:
        pytest.skip("set FORY_RT_WRITER and FORY_RT_READER (see scripts/ci/roundtrip.sh)")
    return writer, reader
