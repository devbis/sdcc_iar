from __future__ import annotations

from .models import ModuleRecord


def select_modules(
    modules: list[ModuleRecord],
    needed_symbols: set[str],
    forced_modules: set[str],
) -> list[ModuleRecord]:
    selected: list[ModuleRecord] = []
    for module in modules:
        if module.name in forced_modules or needed_symbols.intersection(module.exports):
            selected.append(module)
    selected.sort(key=lambda module: module.name)
    return selected

