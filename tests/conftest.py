import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: tests d'intégration — appellent le LLM réel et la DB, consomment des tokens",
    )