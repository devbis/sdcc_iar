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

