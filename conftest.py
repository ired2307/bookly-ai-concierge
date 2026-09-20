import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def reset_shared_state():
    """Clear all in-memory write logs before and after every test."""
    from data import PENDING_REFUNDS, REFUNDS_INITIATED
    from server import _contexts, _sessions

    REFUNDS_INITIATED.clear()
    PENDING_REFUNDS.clear()
    _contexts.clear()
    _sessions.clear()
    yield
    REFUNDS_INITIATED.clear()
    PENDING_REFUNDS.clear()
    _contexts.clear()
    _sessions.clear()
