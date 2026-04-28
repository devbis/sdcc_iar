from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re

from .archive import BANKED_MARKERS, extract_strings, extract_symbols
from .heuristics import is_noise_symbol, is_type_symbol
from .models import IarObject, IarRelocation, IarSection, IarSymbol


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
API_SYMBOL_PREFIXES = (
    "Hal",
    "hal",
    "MAC",
    "mac",
    "MT",
    "mt",
    "APS",
    "aps",
    "APSF",
    "apsf",
    "APSDE",
    "apsde",
    "APSME",
    "apsme",
    "AIB",
    "aib",
    "NLME",
    "nlme",
    "NLDE",
    "nlde",
    "AddrMgr",
    "addrMgr",
    "Assoc",
    "assoc",
    "GP",
    "gp",
    "RTG",
    "rtg",
    "Nwk",
    "nwk",
    "NWK",
    "SSP",
    "ssp",
    "BDB",
    "bdb",
    "ZDO",
    "zdo",
    "ZD",
    "zd",
    "ZSE",
    "zse",
    "ZMac",
    "zmac",
)
NOISE_RE = re.compile(r"^(?:_(?:J|nJ)[A-Za-z0-9_]*|_ZZ?[0-9a-z][A-Za-z0-9_]*)$")
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
    "ZSE",
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


def _looks_like_type_symbol(symbol: str) -> bool:
    return is_type_symbol(symbol)


def _looks_like_api_symbol(symbol: str) -> bool:
    name = symbol.lstrip("_")
    return any(name.startswith(prefix) for prefix in API_SYMBOL_PREFIXES)


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
            or is_noise_symbol(symbol)
            or symbol.startswith(NOISE_PREFIXES)
            or NOISE_RE.match(symbol)
        ):
            noise_symbols.append(symbol)
            continue
        if symbol in IMPORT_SYMBOLS or symbol.startswith(IMPORT_PREFIXES):
            imports.append(symbol)
            continue
        if (
            _common_prefix_len(symbol_key, module_key) >= 3
            or any(token in symbol_key for token in module_tokens)
            or any(symbol.lstrip("_").startswith(prefix) for prefix in PUBLIC_EXPORT_PREFIXES)
        ):
            exports.append(symbol)
            continue
        if _looks_like_api_symbol(symbol):
            imports.append(symbol)
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


def _extract_module_name(strings: list[str], path: Path | None = None) -> str:
    if strings:
        return strings[0]
    return path.stem if path is not None else "iar_object"


def _section_kind(name: str) -> str:
    upper = name.upper()
    if upper in {
        "BANKED_CODE",
        "BANK_RELAYS",
        "RCODE",
        "NEAR_CODE",
        "CODE_C",
        "CSTART",
        "DIFUNCT",
        "XDATA_ROM_C_FLASH",
    }:
        return "code"
    if "CODE" in upper:
        return "code"
    if upper == "XDATA_ROM_C":
        return "xdata"
    if "XSTACK" in upper or "XDATA" in upper:
        return "xdata"
    if "ISTACK" in upper or "IDATA" in upper:
        return "idata"
    if "PSTACK" in upper or "PDATA" in upper:
        return "pdata"
    if "DATA_Z" in upper or "DATA_I" in upper or upper == "VREG":
        return "data"
    if "OVERLAY" in upper:
        return "data"
    if "BIT" in upper:
        return "bit"
    return "unknown"


def _extract_sections(data: bytes, strings: list[str]) -> list[IarSection]:
    sections: list[IarSection] = []
    if any(marker in strings for marker in BANKED_MARKERS):
        sections.append(
            IarSection(
                name="BANKED_CODE",
                kind="code",
                size=len(data),
                alignment=1,
                flags={"banked": True},
            )
        )

    seen_named = {section.name for section in sections}
    for token in strings:
        if not token.endswith("K"):
            continue
        if not token.isupper():
            continue
        section_name = token[:-1]
        if not section_name or section_name in seen_named:
            continue
        seen_named.add(section_name)
        sections.append(
            IarSection(
                name=section_name,
                kind=_section_kind(section_name),
                size=0,
                alignment=1,
            )
        )

    if not sections:
        sections.append(IarSection(name="BANKED_CODE", kind="code", size=len(data), alignment=1))

    if not any(section.kind == "code" for section in sections):
        sections.insert(0, IarSection(name="BANKED_CODE", kind="code", size=len(data), alignment=1))

    return sections


def _extract_banked_export_symbols(strings: list[str]) -> set[str]:
    exports: set[str] = set()
    for index in range(len(strings) - 1):
        symbol = strings[index]
        marker = strings[index + 1]
        if marker != "?relay":
            continue
        normalized = f"_{symbol}" if not symbol.startswith(("_", "?")) else symbol
        if normalized in IMPORT_SYMBOLS or normalized.startswith(IMPORT_PREFIXES):
            continue
        exports.add(normalized)
    return exports


def _build_object_symbols(
    module: str,
    calling_convention: str | None,
    strings: list[str],
    sections: list[IarSection],
) -> tuple[list[IarSymbol], list[str], list[str], list[str], list[str]]:
    raw_symbols = extract_symbols(strings)
    exports, imports, noise_symbols, unknown_symbols = classify_symbols(
        module,
        calling_convention,
        raw_symbols,
    )
    banked_exports = _extract_banked_export_symbols(strings)
    if banked_exports:
        export_set = set(exports) | banked_exports
        exports = [symbol for symbol in raw_symbols if symbol in export_set]
        imports = [symbol for symbol in imports if symbol not in banked_exports]
        noise_symbols = [symbol for symbol in noise_symbols if symbol not in banked_exports]
        unknown_symbols = [symbol for symbol in unknown_symbols if symbol not in banked_exports]

    section_name = next((section.name for section in sections if section.kind == "code"), None)
    object_symbols: list[IarSymbol] = []
    for symbol in exports:
        object_symbols.append(
            IarSymbol(
                name=symbol,
                binding="public",
                section=section_name,
                offset=None,
                is_function=True,
            )
        )
    for symbol in imports:
        object_symbols.append(
            IarSymbol(
                name=symbol,
                binding="external",
                section=None,
                offset=None,
                is_function=not symbol.endswith("_t"),
            )
        )
    for symbol in unknown_symbols:
        object_symbols.append(
            IarSymbol(
                name=symbol,
                binding="local",
                section=section_name,
                offset=None,
                is_function=not symbol.endswith("_t"),
            )
        )
    return object_symbols, exports, imports, noise_symbols, unknown_symbols


def _extract_relocations(
    data: bytes,
    sections: list[IarSection],
    symbols: list[IarSymbol],
    strings: list[str],
) -> tuple[list[IarRelocation], list[str]]:
    relocations: list[IarRelocation] = []
    issues: list[str] = []
    code_section = next((section.name for section in sections if section.kind == "code"), sections[0].name)
    offset = 0
    for symbol in symbols:
        if symbol.binding != "external":
            continue
        relocations.append(
            IarRelocation(
                section=code_section,
                offset=offset,
                kind="abs16",
                target_symbol=symbol.name,
                target_section=None,
                addend=0,
                width=2,
            )
        )
        offset += 2

    for marker in BANKED_MARKERS:
        if marker not in strings:
            continue
        relocations.append(
            IarRelocation(
                section=code_section,
                offset=offset,
                kind="abs16",
                target_symbol=marker,
                target_section=None,
                addend=0,
                width=2,
            )
        )
        offset += 2

    if not relocations:
        relocations.append(
            IarRelocation(
                section=code_section,
                offset=0,
                kind="section_rel",
                target_symbol=None,
                target_section=code_section,
                addend=0,
                width=2,
            )
        )
        issues.append(
            "No external relocation records decoded yet; emitted a placeholder section-relative relocation."
        )

    return relocations, issues


def parse_iar_object_bytes(
    data: bytes,
    *,
    source_path: str = "<memory>",
    module_name_hint: str | None = None,
) -> IarObject:
    strings = extract_strings(data)
    module = module_name_hint or _extract_module_name(strings)
    calling_convention = _next_value(strings, "__calling_convention")
    code_model = _next_value(strings, "__code_model")
    data_model = _next_value(strings, "__data_model")
    sections = _extract_sections(data, strings)
    symbols, exports, imports, _, unknown_symbols = _build_object_symbols(
        module,
        calling_convention,
        strings,
        sections,
    )
    relocations, relocation_issues = _extract_relocations(data, sections, symbols, strings)
    issues = list(relocation_issues)
    if unknown_symbols:
        issues.append(
            "Unclassified symbols left as local placeholders: " + ", ".join(sorted(unknown_symbols))
        )
    return IarObject(
        module=module,
        source_path=source_path,
        calling_convention=calling_convention,
        code_model=code_model,
        data_model=data_model,
        sections=sections,
        symbols=symbols,
        relocations=relocations,
        issues=issues,
    )


def parse_iar_object(path: Path) -> IarObject:
    return parse_iar_object_bytes(
        path.read_bytes(),
        source_path=str(path.resolve()),
        module_name_hint=None,
    )


def parse_module_summary(path: Path) -> ModuleSummary:
    obj = parse_iar_object(path)
    strings = extract_strings(path.read_bytes())
    symbols = [symbol.name for symbol in obj.symbols]
    exports = [symbol.name for symbol in obj.symbols if symbol.binding == "public"]
    imports = [symbol.name for symbol in obj.symbols if symbol.binding == "external"]
    noise_symbols = [
        symbol
        for symbol in extract_symbols(strings)
        if symbol not in exports and symbol not in imports and NOISE_RE.match(symbol)
    ]
    unknown_symbols = [
        symbol.name for symbol in obj.symbols if symbol.binding == "local"
    ]
    return ModuleSummary(
        module=obj.module,
        path=str(path.resolve()),
        size=path.stat().st_size,
        calling_convention=obj.calling_convention,
        code_model=obj.code_model,
        data_model=obj.data_model,
        banked_markers=[marker for marker in BANKED_MARKERS if marker in strings],
        symbols=symbols,
        exports=exports,
        imports=imports,
        noise_symbols=noise_symbols,
        unknown_symbols=unknown_symbols,
        normalized_ir=build_normalized_ir(
            obj.module,
            obj.calling_convention,
            obj.code_model,
            obj.data_model,
            exports,
            imports,
            unknown_symbols,
        ),
    )
