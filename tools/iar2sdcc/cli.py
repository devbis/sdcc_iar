from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__ in (None, ""):
    import sys

    PACKAGE_ROOT = Path(__file__).resolve().parent.parent
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_ROOT))

    from iar2sdcc.archive import normalize_symbol, scan_library
    from iar2sdcc.emitter import emit_stub_library
    from iar2sdcc.linker import parse_undefined_globals
    from iar2sdcc.models import ModuleRecord
    from iar2sdcc.overrides import load_forced_modules
    from iar2sdcc.planning import build_module_candidates
    from iar2sdcc.report import write_manifest, write_report
    from iar2sdcc.selector import select_modules
    from iar2sdcc.workspace import ensure_out_dir
else:
    from .archive import normalize_symbol, scan_library
    from .emitter import emit_stub_library
    from .linker import parse_undefined_globals
    from .models import ModuleRecord
    from .overrides import load_forced_modules
    from .planning import build_module_candidates
    from .report import write_manifest, write_report
    from .selector import select_modules
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

    convert = sub.add_parser("convert")
    convert.add_argument("--manifest", type=Path, required=True)
    convert.add_argument("--out-dir", type=Path, required=True)
    convert.add_argument("--link-log", type=Path)
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
        resolved[symbol] = [
            inventory.library
            for inventory in inventories
            if symbol in inventory.symbols
        ]
    return resolved


def resolve_log(log_path: Path, libraries: list[Path]) -> dict[str, object]:
    references = parse_undefined_globals(log_path.read_text(encoding="utf-8"))
    symbols = list(references)
    inventories = [scan_library(path) for path in libraries]
    library_modules = {
        inventory.library: inventory.modules
        for inventory in inventories
    }
    resolved_symbols = {
        symbol: [
            inventory.library
            for inventory in inventories
            if symbol in inventory.symbols
        ]
        for symbol in symbols
    }
    return {
        "log": str(log_path.resolve()),
        "undefined_symbols": symbols,
        "references": references,
        "libraries": resolved_symbols,
        "library_modules": library_modules,
        "module_candidates": build_module_candidates(library_modules, resolved_symbols),
    }


def summarize_link_resolution(link_resolution: dict[str, object]) -> dict[str, int]:
    libraries = link_resolution["libraries"]
    module_candidates = link_resolution["module_candidates"]
    return {
        "undefined_symbols": len(link_resolution["undefined_symbols"]),
        "symbols_with_owner": sum(1 for matches in libraries.values() if matches),
        "symbols_without_owner": sum(1 for matches in libraries.values() if not matches),
        "symbols_with_module_candidates": sum(
            1
            for symbol_candidates in module_candidates.values()
            if any(candidates for candidates in symbol_candidates.values())
        ),
    }


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
    emitted = [emit_stub_library(workspace, module.name) for module in selected]
    unresolved = sorted(str(symbol) for symbol in manifest.get("required_symbols", []))
    link_resolution = None
    link_resolution_summary = None
    if link_log_path is not None:
        link_resolution = resolve_log(link_log_path, [Path(library) for library in libraries])
        link_resolution_summary = summarize_link_resolution(link_resolution)

    write_manifest(
        workspace / "manifest.json",
        project=project,
        libraries=libraries,
        modules=selected,
        emitted=emitted,
        unresolved=unresolved,
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
            ]
        )
    write_report(
        workspace / "report.txt",
        report_lines,
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
