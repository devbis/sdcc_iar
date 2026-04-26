from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re


BANKED_MARKERS = ("?BDISPATCH", "?BRET", "?BANKED_ENTER_XDATA", "?BANKED_LEAVE_XDATA")
SYMBOL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MODULE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
NOISE_SYMBOLS = {
    "CLib",
    "Status_t",
    "ZStatus_t",
    "bool",
    "uint8",
    "uint16",
    "uint32",
    "data",
    "disabled",
    "large",
    "plain",
}


def extract_strings(data: bytes, min_len: int = 4) -> list[str]:
    strings: list[str] = []
    chunk = bytearray()
    for byte in data:
        if 32 <= byte <= 126:
            chunk.append(byte)
            continue
        if len(chunk) >= min_len:
            strings.append(chunk.decode("ascii", errors="ignore"))
        chunk.clear()
    if len(chunk) >= min_len:
        strings.append(chunk.decode("ascii", errors="ignore"))
    return strings


@dataclass(slots=True)
class ArchiveInventory:
    library: str
    size: int
    strings: list[str]
    banked_markers: list[str]
    symbols: list[str]
    modules: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ModuleSpan:
    name: str
    start_offset: int
    end_offset: int

    @property
    def size(self) -> int:
        return self.end_offset - self.start_offset

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "size": self.size,
        }


def normalize_symbol(token: str) -> str:
    if token.startswith(("_", "?")):
        return token
    return f"_{token}"


def is_candidate_symbol(token: str) -> bool:
    if token in NOISE_SYMBOLS:
        return False
    if token.startswith("__"):
        return False
    if token.startswith("?"):
        return False
    if not SYMBOL_RE.match(token):
        return False
    return "_" in token or any(ch.islower() for ch in token) and any(ch.isupper() for ch in token)


def extract_symbols(strings: list[str]) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for token in strings:
        if not is_candidate_symbol(token):
            continue
        normalized = normalize_symbol(token)
        if normalized in seen:
            continue
        seen.add(normalized)
        symbols.append(normalized)
    return symbols


def extract_modules(strings: list[str]) -> list[str]:
    modules: list[str] = []
    seen: set[str] = set()
    for index in range(len(strings) - 3):
        candidate = strings[index]
        if strings[index + 1] != "10.20":
            continue
        if strings[index + 2] != "__SystemLibrary":
            continue
        if strings[index + 3] != "CLib":
            continue
        if not MODULE_NAME_RE.match(candidate):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        modules.append(candidate)
    return modules


def extract_strings_with_offsets(data: bytes, min_len: int = 4) -> list[tuple[int, str]]:
    strings: list[tuple[int, str]] = []
    chunk = bytearray()
    start: int | None = None
    for index, byte in enumerate(data):
        if 32 <= byte <= 126:
            if start is None:
                start = index
            chunk.append(byte)
            continue
        if len(chunk) >= min_len and start is not None:
            strings.append((start, chunk.decode("ascii", errors="ignore")))
        chunk.clear()
        start = None
    if len(chunk) >= min_len and start is not None:
        strings.append((start, chunk.decode("ascii", errors="ignore")))
    return strings


def extract_module_spans(data: bytes) -> list[ModuleSpan]:
    strings = extract_strings_with_offsets(data)
    starts: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for index in range(len(strings) - 3):
        offset, candidate = strings[index]
        if strings[index + 1][1] != "10.20":
            continue
        if strings[index + 2][1] != "__SystemLibrary":
            continue
        if strings[index + 3][1] != "CLib":
            continue
        if not MODULE_NAME_RE.match(candidate):
            continue
        key = (candidate, offset)
        if key in seen:
            continue
        seen.add(key)
        starts.append((candidate, offset))

    spans: list[ModuleSpan] = []
    for index, (name, start_offset) in enumerate(starts):
        end_offset = starts[index + 1][1] if index + 1 < len(starts) else len(data)
        spans.append(ModuleSpan(name=name, start_offset=start_offset, end_offset=end_offset))
    return spans


def scan_library(path: Path) -> ArchiveInventory:
    data = path.read_bytes()
    strings = extract_strings(data)
    markers = [marker for marker in BANKED_MARKERS if marker in strings]
    symbols = extract_symbols(strings)
    modules = extract_modules(strings)
    return ArchiveInventory(
        library=str(path.resolve()),
        size=len(data),
        strings=strings[:256],
        banked_markers=markers,
        symbols=symbols,
        modules=modules,
    )
