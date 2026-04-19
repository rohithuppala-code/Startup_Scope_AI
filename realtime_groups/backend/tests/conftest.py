# realtime_groups/backend/tests/conftest.py
# ---------------------------------------------------------------------------
# Shared pytest configuration for the social module test suite.
# - Inserts project root onto sys.path so `realtime_groups` is importable.
# - Registers asyncio_mode = auto for all async tests/fixtures.
# ---------------------------------------------------------------------------
import sys
from pathlib import Path

import pytest

# Ensure the Startup_Scope_AI root is on the path so
# `import realtime_groups.*` always resolves.
# Path: conftest.py → tests/ → backend/ → realtime_groups/ → Startup_Scope_AI
#                      [0]       [1]          [2]                [3]
PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# Tell pytest-asyncio to auto-detect async tests and fixtures.
pytest_plugins = ("pytest_asyncio",)
