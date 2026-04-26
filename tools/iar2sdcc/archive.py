from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


BANKED_MARKERS = ("?BDISPATCH", "?BRET", "?BANKED_ENTER_XDATA", "?BANKED_LEAVE_XDATA")


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

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def scan_library(path: Path) -> ArchiveInventory:
    data = path.read_bytes()
    strings = extract_strings(data)
    markers = [marker for marker in BANKED_MARKERS if marker in strings]
    return ArchiveInventory(
        library=str(path.resolve()),
        size=len(data),
        strings=strings[:256],
        banked_markers=markers,
    )

