from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .archive import BANKED_MARKERS, extract_strings, extract_symbols


def parse_module_names(path: Path) -> list[str]:
    return [path.stem]


def _next_value(strings: list[str], key: str) -> str | None:
    for index, value in enumerate(strings):
        if value != key:
            continue
        if index + 1 < len(strings):
            return strings[index + 1]
    return None


@dataclass(slots=True)
class ModuleSummary:
    module: str
    path: str
    size: int
    calling_convention: str | None
    code_model: str | None
    data_model: str | None
    banked_markers: list[str]
    symbols: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_module_summary(path: Path) -> ModuleSummary:
    data = path.read_bytes()
    strings = extract_strings(data)
    module = strings[0] if strings else path.stem
    return ModuleSummary(
        module=module,
        path=str(path.resolve()),
        size=len(data),
        calling_convention=_next_value(strings, "__calling_convention"),
        code_model=_next_value(strings, "__code_model"),
        data_model=_next_value(strings, "__data_model"),
        banked_markers=[marker for marker in BANKED_MARKERS if marker in strings],
        symbols=extract_symbols(strings),
    )
