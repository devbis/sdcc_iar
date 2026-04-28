from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

if __package__ in (None, ""):
    import sys

    PACKAGE_ROOT = Path(__file__).resolve().parent.parent
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_ROOT))

    from iar2sdcc.archive import extract_module_spans, normalize_symbol, scan_library
    from iar2sdcc.emitter import (
        emit_auto_stub_module,
        emit_fallback_stub,
        emit_ownerless_stub,
        emit_stub_library,
    )
    from iar2sdcc.linker import parse_undefined_globals
    from iar2sdcc.models import ModuleRecord
    from iar2sdcc.object_parser import parse_iar_object, parse_iar_object_bytes, parse_module_summary
    from iar2sdcc.overrides import load_forced_modules
    from iar2sdcc.planning import build_module_candidates, build_module_plan
    from iar2sdcc.rel_emitter import emit_converted_rel
    from iar2sdcc.report import write_json, write_manifest, write_report
    from iar2sdcc.selector import select_modules
    from iar2sdcc.slices import export_module_slices
    from iar2sdcc.workspace import ensure_out_dir
else:
    from .archive import extract_module_spans, normalize_symbol, scan_library
    from .emitter import (
        emit_auto_stub_module,
        emit_fallback_stub,
        emit_ownerless_stub,
        emit_stub_library,
    )
    from .linker import parse_undefined_globals
    from .models import ModuleRecord
    from .object_parser import parse_iar_object, parse_iar_object_bytes, parse_module_summary
    from .overrides import load_forced_modules
    from .planning import build_module_candidates, build_module_plan
    from .rel_emitter import emit_converted_rel
    from .report import write_json, write_manifest, write_report
    from .selector import select_modules
    from .slices import export_module_slices
    from .workspace import ensure_out_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iar2sdcc")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan")
    scan.add_argument("library", type=Path)
    scan.add_argument("--json", action="store_true")

    resolve = sub.add_parser("resolve")
    resolve.add_argument("items", nargs="+")
    resolve.add_argument("--json", action="store_true")

    resolve_log = sub.add_parser("resolve-log")
    resolve_log.add_argument("log", type=Path)
    resolve_log.add_argument("libraries", nargs="+", type=Path)
    resolve_log.add_argument("--json", action="store_true")

    inspect_slice = sub.add_parser("inspect-slice")
    inspect_slice.add_argument("slice", type=Path)
    inspect_slice.add_argument("--json", action="store_true")

    inspect_object = sub.add_parser("inspect-object")
    inspect_object.add_argument("object", type=Path)
    inspect_object.add_argument("--json", action="store_true")

    convert = sub.add_parser("convert")
    convert.add_argument("--manifest", type=Path, required=True)
    convert.add_argument("--out-dir", type=Path, required=True)
    convert.add_argument("--link-log", type=Path)

    convert_object = sub.add_parser("convert-object")
    convert_object.add_argument("object", type=Path)
    convert_object.add_argument("--out-dir", type=Path, required=True)
    return parser


def default_override_path(manifest_path: Path) -> Path:
    return manifest_path.parent.parent / "overrides" / f"{manifest_path.stem}.yaml"


def load_project_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def split_resolve_items(items: list[str]) -> tuple[list[Path], list[str]]:
    libraries: list[Path] = []
    symbols: list[str] = []
    for item in items:
        path = Path(item)
        if path.exists():
            libraries.append(path)
        else:
            symbols.append(normalize_symbol(item))
    return libraries, symbols


def resolve_symbols(libraries: list[Path], symbols: list[str]) -> dict[str, list[str]]:
    inventories = [scan_library(path) for path in libraries]
    resolved: dict[str, list[str]] = {}
    for symbol in symbols:
        matches = [
            inventory.library
            for inventory in inventories
            if symbol in inventory.symbols
        ]
        if not matches:
            base_symbol = normalize_symbol(symbol)
            base_symbol = base_symbol.rsplit("_PARM_", 1)[0] if "_PARM_" in base_symbol else base_symbol
            if base_symbol != symbol:
                matches = [
                    inventory.library
                    for inventory in inventories
                    if base_symbol in inventory.symbols
                ]
        resolved[symbol] = matches
    return resolved


def build_library_export_index(libraries: list[Path]) -> dict[str, dict[str, list[str]]]:
    index: dict[str, dict[str, list[str]]] = {}
    for library in libraries:
        data = library.read_bytes()
        exports_by_symbol: dict[str, set[str]] = {}
        for span in extract_module_spans(data):
            obj = parse_iar_object_bytes(
                data[span.start_offset:span.end_offset],
                source_path=f"{library.resolve()}!{span.name}",
                module_name_hint=span.name,
            )
            module_exports = [symbol.name for symbol in obj.symbols if symbol.binding == "public"]
            for symbol_name in module_exports:
                exports_by_symbol.setdefault(symbol_name, set()).add(span.name)
        index[str(library.resolve())] = {
            symbol_name: sorted(module_names)
            for symbol_name, module_names in exports_by_symbol.items()
        }
    return index


def _library_dirname(library: str) -> str:
    stem = Path(library).stem
    return stem.replace(".lib", "")


def _resolve_metadata_library(
    payload: dict[str, object],
    known_libraries: set[str],
    library_dirnames: dict[str, str],
) -> str | None:
    source_library = payload.get("source_library")
    if isinstance(source_library, str):
        normalized = str(Path(source_library).resolve())
        if normalized in known_libraries:
            return normalized

    source_path = payload.get("source_path")
    if not isinstance(source_path, str):
        return None

    parts = Path(source_path).parts
    try:
        index = parts.index("module-slices")
    except ValueError:
        return None
    if index + 1 >= len(parts):
        return None

    library_dir = parts[index + 1]
    for library, dirname in library_dirnames.items():
        if dirname == library_dir:
            return library
    return None


def _is_existing_import_candidate(symbol: str) -> bool:
    if "_PARM_" in symbol:
        return True
    if symbol.endswith("_t"):
        return True
    if symbol.startswith(
        (
            "_AIB_",
            "_NIB",
            "_saved",
            "_ZLongAddr",
            "_sAddr",
            "_Reflect",
            "_BindingEntry",
            "_ResultList",
            "_osal_event_hdr",
            "_osal_msg_q",
            "_ZMac",
            "_ZNwk",
        )
    ):
        return True
    if symbol.startswith(
        (
            "_APSME_",
            "_APSDE_",
            "_APSF_",
            "_APS_",
            "_NLME_",
            "_NLDE_",
            "_MAC_",
            "_MT_",
            "_SSP_",
            "_AddrMgr",
            "_Assoc",
            "_RTG_",
            "_ZDO_",
            "_ZDP_",
            "_gp_",
            "_GP_",
            "_nwk",
            "_aps_",
            "_af",
        )
    ):
        return False
    return symbol[1:2].isupper()


def build_existing_module_symbol_index(
    workspace: Path,
    libraries: list[Path],
) -> dict[str, dict[str, list[str]]]:
    known_libraries = {str(path.resolve()) for path in libraries}
    library_dirnames = {
        str(path.resolve()): _library_dirname(str(path.resolve()))
        for path in libraries
    }
    allowed_modules = {
        str(path.resolve()): set(scan_library(path).modules)
        for path in libraries
    }
    index: dict[str, dict[str, set[str]]] = {}

    for metadata_path in workspace.glob("*.convert.json"):
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        library = _resolve_metadata_library(payload, known_libraries, library_dirnames)
        module = payload.get("module")
        if library is None or not isinstance(module, str):
            continue
        if module not in allowed_modules.get(library, set()):
            continue
        symbols = set()
        for key in ("exports", "locals", "forced_exports"):
            values = payload.get(key, [])
            if isinstance(values, list):
                symbols.update(symbol for symbol in values if isinstance(symbol, str))
        import_values = payload.get("imports", [])
        if isinstance(import_values, list):
            symbols.update(
                symbol
                for symbol in import_values
                if isinstance(symbol, str) and _is_existing_import_candidate(symbol)
            )
        if not symbols:
            continue
        for symbol in symbols:
            index.setdefault(library, {}).setdefault(symbol, set()).add(module)

    return {
        library: {
            symbol: sorted(modules)
            for symbol, modules in symbols.items()
        }
        for library, symbols in index.items()
    }


def resolve_log(
    log_path: Path,
    libraries: list[Path],
    existing_module_symbols: dict[str, dict[str, list[str]]] | None = None,
) -> dict[str, object]:
    references = parse_undefined_globals(log_path.read_text(encoding="utf-8"))
    symbols = list(references)
    inventories = [scan_library(path) for path in libraries]
    library_modules = {
        inventory.library: inventory.modules
        for inventory in inventories
    }
    exact_module_exports = build_library_export_index(libraries)
    resolved_symbols = resolve_symbols(libraries, symbols)
    module_candidates = build_module_candidates(
        library_modules,
        resolved_symbols,
        exact_module_exports,
        existing_module_symbols,
    )
    return {
        "log": str(log_path.resolve()),
        "undefined_symbols": symbols,
        "references": references,
        "libraries": resolved_symbols,
        "library_modules": library_modules,
        "exact_module_exports": exact_module_exports,
        "module_candidates": module_candidates,
        "module_plan": build_module_plan(module_candidates),
    }


def summarize_link_resolution(link_resolution: dict[str, object]) -> dict[str, int]:
    libraries = link_resolution["libraries"]
    module_candidates = link_resolution["module_candidates"]
    module_plan = link_resolution["module_plan"]
    module_slices = link_resolution.get("module_slices", {})
    return {
        "undefined_symbols": len(link_resolution["undefined_symbols"]),
        "symbols_with_owner": sum(1 for matches in libraries.values() if matches),
        "symbols_without_owner": sum(1 for matches in libraries.values() if not matches),
        "symbols_with_module_candidates": sum(
            1
            for symbol_candidates in module_candidates.values()
            if any(candidates for candidates in symbol_candidates.values())
        ),
        "planned_modules": sum(len(records) for records in module_plan.values()),
        "exported_module_slices": sum(len(records) for records in module_slices.values()),
    }


def _convert_module_slice(
    workspace: Path,
    source_library: str,
    slice_entry: dict[str, object],
    plan_entry: dict[str, object],
) -> tuple[str, str]:
    slice_path = Path(str(slice_entry["path"]))
    normalized_ir: dict[str, object] = {}
    ir_path = slice_entry.get("ir_path")
    if ir_path is not None:
        normalized_ir = json.loads(Path(str(ir_path)).read_text(encoding="utf-8"))
    try:
        obj = parse_iar_object_bytes(
            slice_path.read_bytes(),
            source_path=str(slice_path.resolve()),
            module_name_hint=str(plan_entry["module"]),
        )
        previous_exports: list[str] = []
        previous_metadata = workspace / f"{obj.module}.convert.json"
        if previous_metadata.exists():
            try:
                payload = json.loads(previous_metadata.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            prior = payload.get("emitted_exports", [])
            if isinstance(prior, list):
                previous_exports = [symbol for symbol in prior if isinstance(symbol, str)]
        rel_path = workspace / f"{obj.module}.rel"
        metadata_path = workspace / f"{obj.module}.convert.json"
        emit_converted_rel(
            obj,
            rel_path,
            metadata_path,
            source_library=source_library,
            required_exports=list(dict.fromkeys(previous_exports + list(plan_entry["symbols"]))),
            normalized_ir=normalized_ir,
        )
        return str(rel_path), "object"
    except (OSError, subprocess.CalledProcessError, ValueError):
        rel_path = emit_auto_stub_module(
            workspace,
            str(plan_entry["module"]),
            list(plan_entry["symbols"]),
            normalized_ir,
        )
        return rel_path, "auto_stub"


def _load_existing_emitted_artifacts(workspace: Path) -> list[str]:
    manifest_path = workspace / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    artifacts = payload.get("emitted_artifacts", [])
    if not isinstance(artifacts, list):
        return []

    preserved: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, str):
            continue
        artifact_path = Path(artifact)
        if artifact_path.exists():
            preserved.append(str(artifact_path))
    return preserved


def convert_project(
    manifest_path: Path,
    out_dir: Path,
    link_log_path: Path | None = None,
) -> dict[str, object]:
    project = manifest_path.stem
    manifest = load_project_manifest(manifest_path)
    libraries = [str(Path(lib)) for lib in manifest.get("iar_libraries", [])]

    forced_modules = load_forced_modules(default_override_path(manifest_path))
    modules = [ModuleRecord(name=name, exports=[], imports=[]) for name in sorted(forced_modules)]
    selected = select_modules(modules, needed_symbols=set(), forced_modules=forced_modules)

    workspace = ensure_out_dir(out_dir)
    emitted = _load_existing_emitted_artifacts(workspace) if link_log_path is not None else []
    emitted.extend(emit_stub_library(workspace, module.name) for module in selected)
    emitted = list(dict.fromkeys(emitted))
    manifest_required_symbols = sorted(str(symbol) for symbol in manifest.get("required_symbols", []))
    unresolved = list(manifest_required_symbols)
    link_resolution = None
    link_resolution_summary = None
    if link_log_path is not None:
        library_paths = [Path(library) for library in libraries]
        existing_module_symbols = build_existing_module_symbol_index(workspace, library_paths)
        link_resolution = resolve_log(
            link_log_path,
            library_paths,
            existing_module_symbols=existing_module_symbols,
        )
        unresolved = sorted(str(symbol) for symbol in link_resolution["undefined_symbols"])
        link_resolution["module_slices"] = export_module_slices(workspace, link_resolution["module_plan"])
        planned_symbols: set[str] = set()
        for library, plan_entries in link_resolution["module_plan"].items():
            slice_entries = {
                entry["module"]: entry
                for entry in link_resolution["module_slices"].get(library, [])
            }
            for plan_entry in plan_entries:
                planned_symbols.update(plan_entry["symbols"])
                slice_entry = slice_entries.get(plan_entry["module"])
                if slice_entry is not None:
                    artifact_path, conversion_mode = _convert_module_slice(
                        workspace,
                        library,
                        slice_entry,
                        plan_entry,
                    )
                    emitted.append(artifact_path)
                    slice_entry["conversion_mode"] = conversion_mode
                    if conversion_mode == "object":
                        slice_entry["rel_path"] = artifact_path
                        slice_entry["metadata_path"] = str(
                            workspace / f"{plan_entry['module']}.convert.json"
                        )
                    continue
                emitted.append(
                    emit_fallback_stub(workspace, str(plan_entry["module"]), list(plan_entry["symbols"]))
                )
        ownerless_symbols = [
            symbol
            for symbol, matches in link_resolution["libraries"].items()
            if not matches
        ]
        emitted_symbols = set(planned_symbols) | set(ownerless_symbols)
        if ownerless_symbols:
            emitted.append(emit_ownerless_stub(workspace, ownerless_symbols))
        supplemental_symbols = [
            symbol
            for symbol in link_resolution["undefined_symbols"]
            if symbol not in emitted_symbols
        ]
        if supplemental_symbols:
            emitted.append(emit_fallback_stub(workspace, "remaining", supplemental_symbols))
        link_resolution_summary = summarize_link_resolution(link_resolution)
    emitted = list(dict.fromkeys(emitted))

    write_manifest(
        workspace / "manifest.json",
        project=project,
        libraries=libraries,
        modules=selected,
        emitted=emitted,
        unresolved=unresolved,
        manifest_required_symbols=manifest_required_symbols,
        link_resolution=link_resolution,
    )
    report_lines = [
        "conversion staged",
        f"project={project}",
        f"libraries={len(libraries)}",
        f"selected_modules={len(selected)}",
        f"emitted_artifacts={len(emitted)}",
    ]
    if link_resolution_summary is not None:
        report_lines.extend(
            [
                f"link_log={link_resolution['log']}",
                f"link_undefined_symbols={link_resolution_summary['undefined_symbols']}",
                f"link_symbols_with_owner={link_resolution_summary['symbols_with_owner']}",
                f"link_symbols_without_owner={link_resolution_summary['symbols_without_owner']}",
                f"link_symbols_with_module_candidates={link_resolution_summary['symbols_with_module_candidates']}",
                f"link_planned_modules={link_resolution_summary['planned_modules']}",
                f"link_exported_module_slices={link_resolution_summary['exported_module_slices']}",
            ]
        )
    write_report(
        workspace / "report.txt",
        report_lines,
    )
    if link_resolution is not None:
        write_json(
            workspace / "module-plan.json",
            {
                "project": project,
                "log": link_resolution["log"],
                "module_plan": link_resolution["module_plan"],
                "module_slices": link_resolution["module_slices"],
                "summary": link_resolution_summary,
            },
        )

    payload = {
        "project": project,
        "libraries": libraries,
        "selected_modules": [module.name for module in selected],
        "emitted_artifacts": emitted,
        "unresolved_symbols": unresolved,
    }
    if link_resolution is not None:
        payload["link_resolution"] = link_resolution
        payload["link_resolution_summary"] = link_resolution_summary
    return payload


def convert_object(path: Path, out_dir: Path) -> dict[str, object]:
    workspace = ensure_out_dir(out_dir)
    obj = parse_iar_object(path)
    rel_path = workspace / f"{obj.module}.rel"
    metadata_path = workspace / f"{obj.module}.convert.json"
    emit_converted_rel(obj, rel_path, metadata_path)
    payload = {
        "module": obj.module,
        "object": str(path.resolve()),
        "rel_path": str(rel_path),
        "metadata_path": str(metadata_path),
        "issues": obj.issues,
    }
    write_json(workspace / "manifest.json", payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scan":
        payload = scan_library(args.library).to_dict()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Library: {payload['library']}")
            print(f"Size: {payload['size']}")
            print(f"Banked markers: {', '.join(payload['banked_markers']) or 'none'}")
            print(f"Symbols: {len(payload['symbols'])}")
        return 0

    if args.command == "resolve":
        libraries, symbols = split_resolve_items(args.items)
        payload = resolve_symbols(libraries, symbols)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for symbol, matches in payload.items():
                print(f"{symbol}: {', '.join(matches) if matches else 'unresolved'}")
        return 0

    if args.command == "convert":
        payload = convert_project(args.manifest, args.out_dir, args.link_log)
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "convert-object":
        payload = convert_object(args.object, args.out_dir)
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "inspect-object":
        obj = parse_iar_object(args.object)
        payload = {
            "module": obj.module,
            "source_path": obj.source_path,
            "calling_convention": obj.calling_convention,
            "code_model": obj.code_model,
            "data_model": obj.data_model,
            "sections": [
                {
                    "name": section.name,
                    "kind": section.kind,
                    "size": section.size,
                    "alignment": section.alignment,
                }
                for section in obj.sections
            ],
            "symbols": [
                {
                    "name": symbol.name,
                    "binding": symbol.binding,
                    "section": symbol.section,
                    "offset": symbol.offset,
                    "is_function": symbol.is_function,
                }
                for symbol in obj.symbols
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
            "issues": obj.issues,
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Module: {payload['module']}")
            print(f"Path: {payload['source_path']}")
            print(f"Calling convention: {payload['calling_convention'] or 'unknown'}")
            print(f"Code model: {payload['code_model'] or 'unknown'}")
            print(f"Data model: {payload['data_model'] or 'unknown'}")
            print(f"Sections: {len(payload['sections'])}")
            print(f"Symbols: {len(payload['symbols'])}")
            print(f"Relocations: {len(payload['relocations'])}")
        return 0

    if args.command == "inspect-slice":
        payload = parse_module_summary(args.slice).to_dict()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Module: {payload['module']}")
            print(f"Path: {payload['path']}")
            print(f"Size: {payload['size']}")
            print(f"Calling convention: {payload['calling_convention'] or 'unknown'}")
            print(f"Code model: {payload['code_model'] or 'unknown'}")
            print(f"Data model: {payload['data_model'] or 'unknown'}")
            print(f"Banked markers: {', '.join(payload['banked_markers']) or 'none'}")
            print(f"Symbols: {len(payload['symbols'])}")
        return 0

    if args.command == "resolve-log":
        payload = resolve_log(args.log, args.libraries)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for symbol in payload["undefined_symbols"]:
                modules = ", ".join(payload["references"][symbol])
                libraries = payload["libraries"][symbol]
                matches = ", ".join(libraries) if libraries else "unresolved"
                print(f"{symbol}: modules={modules}; libraries={matches}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
