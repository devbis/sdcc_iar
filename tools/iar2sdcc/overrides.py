from __future__ import annotations

from pathlib import Path


def load_forced_modules(path: Path) -> set[str]:
    if not path.exists():
        return set()

    forced: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            forced.add(line[2:].strip())
    return forced

