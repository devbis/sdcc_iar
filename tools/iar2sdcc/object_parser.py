from __future__ import annotations

from pathlib import Path


def parse_module_names(path: Path) -> list[str]:
    return [path.stem]

