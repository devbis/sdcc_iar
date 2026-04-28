from __future__ import annotations

import json
from pathlib import Path

from .emitter import _assemble_source, _identifier
from .models import IarObject, IarSection


AREA_MEMORY_BY_KIND = {
    "bit": "DATA",
    "code": "CODE",
    "data": "DATA",
    "idata": "DATA",
    "pdata": "DATA",
    "xdata": "XDATA",
}

SECTION_ROLE_OVERRIDES = {
    "BANKED_CODE": "banked_code",
    "BANK_RELAYS": "bank_relays",
    "RCODE": "root_code",
    "NEAR_CODE": "near_code",
    "CODE_C": "code_const",
    "CSTART": "startup_code",
    "DIFUNCT": "root_code",
    "XDATA_ROM_C": "xdata_rom_alias",
    "XDATA_ROM_C_FLASH": "xdata_rom_flash_init",
    "XDATA_I": "xdata_init",
    "XDATA_Z": "xdata_zero",
    "XDATA_N": "xdata_noinit",
    "XDATA_ID": "xdata_identity",
    "ISTACK": "istack",
    "PSTACK": "pstack",
    "XSTACK": "xstack",
    "IOVERLAY": "overlay_data",
    "DOVERLAY": "overlay_data",
}

CODE_ROLE_PREFERENCE = {
    "startup_code": 0,
    "bank_relays": 1,
    "root_code": 2,
    "near_code": 3,
    "code_const": 4,
    "banked_code": 5,
    "plain_code": 6,
}

DATA_ROLE_PREFERENCE = {
    "xdata_init": 0,
    "xdata_zero": 1,
    "xdata_noinit": 2,
    "xdata_identity": 3,
    "xdata_rom_alias": 4,
    "overlay_data": 5,
    "xdata": 6,
    "pdata": 7,
    "idata": 8,
    "data": 9,
    "bit": 10,
}


def _is_data_export(symbol_name: str) -> bool:
    return symbol_name.endswith("_t") or (symbol_name.startswith("_p") and symbol_name[2:3].isupper())


def _is_data_symbol(symbol_name: str, normalized_ir: dict[str, object] | None = None) -> bool:
    normalized_ir = normalized_ir or {}
    if symbol_name in normalized_ir.get("data_symbols", []):
        return True
    if "_PARM_" in symbol_name:
        return True
    if _is_data_export(symbol_name):
        return True
    if symbol_name.endswith(("TaskID", "Counter")):
        return True
    if symbol_name.startswith(
        (
            "_AIB_",
            "_NIB",
            "_saved",
            "_Gp",
            "_gp_TaskID",
            "_sAddr",
            "_ZLongAddr",
            "_ZMac",
            "_ZNwk",
            "_BindingEntry",
            "_Reflect",
            "_ResultList",
            "_osal_event_hdr",
        )
    ):
        return True
    return False


def _symbol_lists(obj: IarObject) -> tuple[list[str], list[str], list[str]]:
    exports = [symbol.name for symbol in obj.symbols if symbol.binding == "public"]
    imports = [symbol.name for symbol in obj.symbols if symbol.binding == "external"]
    locals_ = [symbol.name for symbol in obj.symbols if symbol.binding == "local"]
    return exports, imports, locals_


def _sanitize_area_name(name: str) -> str:
    ident = _identifier(name).upper()
    return ident[:32] or "IAR2SDCC"


def _section_role(section: IarSection) -> str:
    upper = section.name.upper()
    if upper in SECTION_ROLE_OVERRIDES:
        return SECTION_ROLE_OVERRIDES[upper]
    if section.kind == "code":
        if section.flags.get("banked"):
            return "banked_code"
        return "plain_code"
    if section.kind == "xdata":
        return "xdata"
    if section.kind == "pdata":
        return "pdata"
    if section.kind == "idata":
        return "idata"
    if section.kind == "data":
        return "data"
    if section.kind == "bit":
        return "bit"
    return "unknown"


def _section_descriptor(section: IarSection) -> dict[str, object]:
    role = _section_role(section)
    banked = bool(section.flags.get("banked")) or role == "banked_code"
    return {
        "name": _sanitize_area_name(section.name),
        "memory": AREA_MEMORY_BY_KIND.get(section.kind, "UNKNOWN"),
        "kind": section.kind,
        "banked": banked,
        "role": role,
        "source_section": section.name,
    }


def _select_function_area(obj: IarObject, section_descriptors: list[dict[str, object]]) -> tuple[str, str]:
    code_descriptors = [descriptor for descriptor in section_descriptors if descriptor["memory"] == "CODE"]
    if code_descriptors:
        ranked = sorted(
            code_descriptors,
            key=lambda descriptor: (
                CODE_ROLE_PREFERENCE.get(str(descriptor["role"]), 100),
                str(descriptor["source_section"]),
            ),
        )
        if obj.code_model == "banked":
            for descriptor in ranked:
                if descriptor["banked"]:
                    return str(descriptor["name"]), str(descriptor["memory"])
        chosen = ranked[0]
        return str(chosen["name"]), str(chosen["memory"])

    if obj.code_model == "banked":
        return "BANKED_CODE", "CODE"
    return "CSEG", "CODE"


def _select_data_area(obj: IarObject, section_descriptors: list[dict[str, object]]) -> tuple[str, str]:
    data_descriptors = [
        descriptor
        for descriptor in section_descriptors
        if descriptor["memory"] in {"XDATA", "PDATA", "DATA", "BIT"}
    ]
    if data_descriptors:
        ranked = sorted(
            data_descriptors,
            key=lambda descriptor: (
                DATA_ROLE_PREFERENCE.get(str(descriptor["role"]), 100),
                str(descriptor["source_section"]),
            ),
        )
        chosen = ranked[0]
        return str(chosen["name"]), str(chosen["memory"])

    if obj.data_model == "large":
        return "XSEG", "XDATA"
    return "DSEG", "DATA"


def _area_plan(obj: IarObject) -> dict[str, object]:
    section_descriptors = [_section_descriptor(section) for section in obj.sections]
    function_area_name, function_area_memory = _select_function_area(obj, section_descriptors)
    data_area_name, data_area_memory = _select_data_area(obj, section_descriptors)
    section_area_map = {
        str(descriptor["source_section"]): {
            "name": descriptor["name"],
            "memory": descriptor["memory"],
            "kind": descriptor["kind"],
            "role": descriptor["role"],
            "banked": descriptor["banked"],
        }
        for descriptor in section_descriptors
    }
    return {
        "function_area": {
            "name": function_area_name,
            "memory": function_area_memory,
            "banked": obj.code_model == "banked",
        },
        "data_area": {
            "name": data_area_name,
            "memory": data_area_memory,
        },
        "available_areas": section_descriptors,
        "section_area_map": section_area_map,
        "root_code_areas": [
            descriptor["name"]
            for descriptor in section_descriptors
            if descriptor["memory"] == "CODE"
            and descriptor["role"] in {"startup_code", "bank_relays", "root_code", "near_code", "code_const"}
        ],
        "banked_code_areas": [
            descriptor["name"]
            for descriptor in section_descriptors
            if descriptor["memory"] == "CODE" and descriptor["banked"]
        ],
        "xdata_areas": [
            descriptor["name"]
            for descriptor in section_descriptors
            if descriptor["memory"] == "XDATA"
        ],
    }


def _metadata_payload(
    obj: IarObject,
    rel_path: Path,
    *,
    source_library: str | None,
    exports: list[str],
    emitted_exports: list[str],
    imports: list[str],
    locals_: list[str],
    forced_exports: list[str],
) -> dict[str, object]:
    area_plan = _area_plan(obj)
    return {
        "module": obj.module,
        "source_path": obj.source_path,
        "source_library": source_library,
        "rel_path": str(rel_path),
        "conversion_mode": "banked_prototype_asm" if obj.code_model == "banked" else "prototype_asm",
        "calling_convention": obj.calling_convention,
        "code_model": obj.code_model,
        "data_model": obj.data_model,
        "exports": exports,
        "emitted_exports": emitted_exports,
        "imports": imports,
        "locals": locals_,
        "forced_exports": forced_exports,
        "sections": [
            {
                "name": section.name,
                "kind": section.kind,
                "size": section.size,
                "alignment": section.alignment,
                "flags": section.flags,
            }
            for section in obj.sections
        ],
        "relocations": [
            {
                "section": relocation.section,
                "offset": relocation.offset,
                "kind": relocation.kind,
                "target_symbol": relocation.target_symbol,
                "target_section": relocation.target_section,
                "addend": relocation.addend,
                "width": relocation.width,
            }
            for relocation in obj.relocations
        ],
        "area_plan": area_plan,
        "issues": obj.issues,
    }


def _emit_area_skeleton(lines: list[str], descriptor: dict[str, object]) -> None:
    if descriptor["memory"] == "UNKNOWN":
        return
    lines.append(f"; area source={descriptor['source_section']} role={descriptor['role']}")
    lines.append(f"\t.area {descriptor['name']}    ({descriptor['memory']})")


def emit_converted_rel(
    obj: IarObject,
    out_rel: Path,
    metadata_path: Path,
    *,
    source_library: str | None = None,
    required_exports: list[str] | None = None,
    normalized_ir: dict[str, object] | None = None,
) -> Path:
    asm_path = out_rel.with_suffix(".converted.asm")
    exports, imports, _ = _symbol_lists(obj)
    locals_ = [symbol.name for symbol in obj.symbols if symbol.binding == "local"]
    required_exports = list(dict.fromkeys(required_exports or []))
    emitted_exports = required_exports if required_exports else list(exports)
    effective_imports = [symbol for symbol in imports if symbol not in emitted_exports]
    functions = [
        symbol
        for symbol in emitted_exports
        if not _is_data_symbol(symbol, normalized_ir)
    ]
    data_exports = [
        symbol
        for symbol in emitted_exports
        if _is_data_symbol(symbol, normalized_ir)
    ]
    area_plan = _area_plan(obj)
    function_area = area_plan["function_area"]
    data_area = area_plan["data_area"]
    available_areas = area_plan["available_areas"]

    lines = [f"; prototype converted module for {obj.module}", f"\t.module {_identifier(obj.module)}"]
    for symbol in sorted(set(emitted_exports + effective_imports)):
        lines.append(f"\t.globl {symbol}")

    primary_area_keys = {
        (data_area["name"], data_area["memory"]),
        (function_area["name"], function_area["memory"]),
    }
    for descriptor in available_areas:
        if (descriptor["name"], descriptor["memory"]) in primary_area_keys:
            continue
        _emit_area_skeleton(lines, descriptor)

    _emit_area_skeleton(
        lines,
        {
            "name": data_area["name"],
            "memory": data_area["memory"],
            "source_section": data_area["name"],
            "role": "primary_data_area",
        },
    )
    if data_exports:
        for symbol in data_exports:
            lines.append(f"{symbol}::")
        lines.append("\t.ds 1")

    _emit_area_skeleton(
        lines,
        {
            "name": function_area["name"],
            "memory": function_area["memory"],
            "source_section": function_area["name"],
            "role": "primary_function_area",
        },
    )
    if functions:
        for symbol in functions:
            lines.append(f"{symbol}::")
        lines.append("\tret")
    elif not data_exports:
        lines.append(f"__iar2sdcc_stub_{_identifier(obj.module)}::")
        lines.append("\tret")

    asm_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _assemble_source(asm_path, out_rel)
    metadata_path.write_text(
        json.dumps(
            _metadata_payload(
                obj,
                out_rel,
                source_library=source_library,
                exports=exports,
                emitted_exports=emitted_exports,
                imports=effective_imports,
                locals_=locals_,
                forced_exports=[symbol for symbol in required_exports if symbol not in exports],
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return out_rel
