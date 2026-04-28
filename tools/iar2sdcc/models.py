from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ConversionIssue:
    severity: str
    message: str
    module: str | None = None


@dataclass(slots=True)
class ModuleRecord:
    name: str
    exports: list[str]
    imports: list[str]
    issues: list[str] = field(default_factory=list)


@dataclass(slots=True)
class IarSection:
    name: str
    kind: str
    size: int
    alignment: int | None = None
    raw_bytes: bytes = b""
    flags: dict[str, bool] = field(default_factory=dict)


@dataclass(slots=True)
class IarSymbol:
    name: str
    binding: str
    section: str | None
    offset: int | None
    size: int | None = None
    is_function: bool | None = None


@dataclass(slots=True)
class IarRelocation:
    section: str
    offset: int
    kind: str
    target_symbol: str | None
    target_section: str | None
    addend: int = 0
    width: int | None = None


@dataclass(slots=True)
class IarObject:
    module: str
    source_path: str
    calling_convention: str | None
    code_model: str | None
    data_model: str | None
    sections: list[IarSection]
    symbols: list[IarSymbol]
    relocations: list[IarRelocation]
    issues: list[str] = field(default_factory=list)
