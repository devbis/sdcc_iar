from __future__ import annotations

import re

from .archive import normalize_symbol
from .heuristics import is_noise_symbol


UNDEFINED_GLOBAL_RE = re.compile(
    r"^\?ASlink-Warning-Undefined Global (?P<symbol>\S+) referenced by module (?P<module>\S+)$"
)


def parse_undefined_globals(text: str) -> dict[str, list[str]]:
    references: dict[str, list[str]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = UNDEFINED_GLOBAL_RE.match(line)
        if match is None:
            continue
        symbol = normalize_symbol(match.group("symbol"))
        if is_noise_symbol(symbol):
            continue
        module = match.group("module")
        modules = references.setdefault(symbol, [])
        if module not in modules:
            modules.append(module)

    return {
        symbol: sorted(modules)
        for symbol, modules in sorted(references.items())
    }
