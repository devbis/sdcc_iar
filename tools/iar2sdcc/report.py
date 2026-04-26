from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import ModuleRecord


def write_manifest(
    path: Path,
    *,
    project: str,
    libraries: list[str],
    modules: list[ModuleRecord],
    emitted: list[str],
    unresolved: list[str],
) -> None:
    payload = {
        "project": project,
        "libraries": libraries,
        "selected_modules": [asdict(module) for module in modules],
        "emitted_artifacts": emitted,
        "unresolved_symbols": unresolved,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_report(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

