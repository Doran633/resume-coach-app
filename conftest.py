from __future__ import annotations

import os
from pathlib import Path


def pytest_configure(config) -> None:
    if os.name != "nt" or config.option.basetemp is not None:
        return

    root = Path(__file__).resolve().parent
    config.option.basetemp = str(root / "backend" / "reports" / f".pytest-windows-{os.getpid()}")
