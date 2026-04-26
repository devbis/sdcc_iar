from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re

from .archive import BANKED_MARKERS, extract_strings, extract_symbols


NOISE_PREFIXES = (
    "_BANK_",
    "_BANKED_",
    "_SFR_",
    "_XDATA_",
    "_CODE_",
)
IMPORT_PREFIXES = (
    "_osal_",
    "_sAddr",
)
IMPORT_SYMBOLS = {
    "_halAssertHandler",
}
NOISE_RE = re.compile(r"^_(?:J|Z|ZZ|nJ)[A-Za-z0-9_]*$")
PUBLIC_EXPORT_PREFIXES = (
    "Hal",
    "SSP",
    "MAC",
    "MT",
    "APS",
    "APSDE",
    "APSME",
    "APSF",
    "NLME",
    "NLDE",
    "AddrMgr",
    "Assoc",
    "GP",
    "RTG",
    "Nwk",
    "NWK",
    "ZDO",
    "ZD",
)


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
    exports: list[str]
    imports: list[str]
    noise_symbols: list[str]
    unknown_symbols: list[str]
    normalized_ir: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _normalize_key(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _common_prefix_len(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def _module_tokens(module: str) -> list[str]:
    raw = [part.lower() for part in re.split(r"[_\-]+", module) if part]
    tokens = [part for part in raw if len(part) >= 3]
    key = _normalize_key(module)
    if len(key) >= 3 and key not in tokens:
        tokens.append(key)
    return tokens


def classify_symbols(
    module: str,
    calling_convention: str | None,
    symbols: list[str],
) -> tuple[list[str], list[str], list[str], list[str]]:
    exports: list[str] = []
    imports: list[str] = []
    noise_symbols: list[str] = []
    unknown_symbols: list[str] = []
    module_symbol = f"_{module}"
    calling_symbol = f"_{calling_convention}" if calling_convention else None
    module_key = _normalize_key(module)
    module_tokens = _module_tokens(module)

    for symbol in symbols:
        symbol_key = _normalize_key(symbol.lstrip("_"))
        if (
            symbol == module_symbol
            or symbol == calling_symbol
            or symbol.startswith(NOISE_PREFIXES)
            or NOISE_RE.match(symbol)
        ):
            noise_symbols.append(symbol)
            continue
        if symbol in IMPORT_SYMBOLS or symbol.startswith(IMPORT_PREFIXES):
            imports.append(symbol)
            continue
        if (
            symbol[1:2].isupper()
            or _common_prefix_len(symbol_key, module_key) >= 3
            or any(token in symbol_key for token in module_tokens)
        ):
            exports.append(symbol)
            continue
        unknown_symbols.append(symbol)

    return exports, imports, noise_symbols, unknown_symbols


def classify_export_visibility(exports: list[str]) -> tuple[list[str], list[str]]:
    public_exports: list[str] = []
    internal_exports: list[str] = []
    for symbol in exports:
        name = symbol.lstrip("_")
        if name.startswith("p") and len(name) > 1 and name[1:2].isupper():
            internal_exports.append(symbol)
            continue
        if name.endswith("_t"):
            internal_exports.append(symbol)
            continue
        if any(name.startswith(prefix) for prefix in PUBLIC_EXPORT_PREFIXES):
            public_exports.append(symbol)
            continue
        internal_exports.append(symbol)
    return public_exports, internal_exports


def _callable_symbols(symbols: list[str]) -> list[str]:
    return [
        symbol
        for symbol in symbols
        if not symbol.endswith("_t") and not (symbol.startswith("_p") and symbol[2:3].isupper())
    ]


def _data_symbols(symbols: list[str]) -> list[str]:
    return [
        symbol
        for symbol in symbols
        if symbol.endswith("_t")
        or (symbol.startswith("_p") and symbol[2:3].isupper())
        or symbol.startswith(("_src", "_dst", "_xfer", "_ctrl", "_dma"))
    ]


def build_normalized_ir(
    module: str,
    calling_convention: str | None,
    code_model: str | None,
    data_model: str | None,
    exports: list[str],
    imports: list[str],
    unknown_symbols: list[str],
) -> dict[str, object]:
    public_exports, internal_exports = classify_export_visibility(exports)
    public_callables = _callable_symbols(public_exports)
    internal_callables = _callable_symbols(internal_exports)
    data_symbols = sorted(
        set(
            _data_symbols(internal_exports)
            + _data_symbols(exports)
            + _data_symbols(imports)
            + _data_symbols(unknown_symbols)
        )
    )
    return {
        "module": module,
        "calling_convention": calling_convention,
        "code_model": code_model,
        "data_model": data_model,
        "public_exports": public_exports,
        "internal_exports": internal_exports,
        "public_callables": public_callables,
        "internal_callables": internal_callables,
        "data_symbols": data_symbols,
        "required_imports": imports,
    }


def parse_module_summary(path: Path) -> ModuleSummary:
    data = path.read_bytes()
    strings = extract_strings(data)
    module = strings[0] if strings else path.stem
    calling_convention = _next_value(strings, "__calling_convention")
    code_model = _next_value(strings, "__code_model")
    data_model = _next_value(strings, "__data_model")
    symbols = extract_symbols(strings)
    exports, imports, noise_symbols, unknown_symbols = classify_symbols(
        module,
        calling_convention,
        symbols,
    )
    return ModuleSummary(
        module=module,
        path=str(path.resolve()),
        size=len(data),
        calling_convention=calling_convention,
        code_model=code_model,
        data_model=data_model,
        banked_markers=[marker for marker in BANKED_MARKERS if marker in strings],
        symbols=symbols,
        exports=exports,
        imports=imports,
        noise_symbols=noise_symbols,
        unknown_symbols=unknown_symbols,
        normalized_ir=build_normalized_ir(
            module,
            calling_convention,
            code_model,
            data_model,
            exports,
            imports,
            unknown_symbols,
        ),
    )
