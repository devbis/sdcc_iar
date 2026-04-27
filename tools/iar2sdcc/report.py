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
    manifest_required_symbols: list[str] | None = None,
    link_resolution: dict[str, object] | None = None,
) -> None:
    payload = {
        "project": project,
        "libraries": libraries,
        "selected_modules": [asdict(module) for module in modules],
        "emitted_artifacts": emitted,
        "unresolved_symbols": unresolved,
    }
    if manifest_required_symbols is not None:
        payload["manifest_required_symbols"] = manifest_required_symbols
    if link_resolution is not None:
        payload["link_resolution"] = link_resolution
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_report(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
