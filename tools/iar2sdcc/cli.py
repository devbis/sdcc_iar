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
    from iar2sdcc.models import ModuleRecord
    from iar2sdcc.overrides import load_forced_modules
    from iar2sdcc.report import write_manifest, write_report
    from iar2sdcc.selector import select_modules
    from iar2sdcc.workspace import ensure_out_dir
else:
    from .archive import normalize_symbol, scan_library
    from .emitter import emit_stub_library
    from .models import ModuleRecord
    from .overrides import load_forced_modules
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

    convert = sub.add_parser("convert")
    convert.add_argument("--manifest", type=Path, required=True)
    convert.add_argument("--out-dir", type=Path, required=True)
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


def convert_project(manifest_path: Path, out_dir: Path) -> dict[str, object]:
    project = manifest_path.stem
    manifest = load_project_manifest(manifest_path)
    libraries = [str(Path(lib)) for lib in manifest.get("iar_libraries", [])]

    forced_modules = load_forced_modules(default_override_path(manifest_path))
    modules = [ModuleRecord(name=name, exports=[], imports=[]) for name in sorted(forced_modules)]
    selected = select_modules(modules, needed_symbols=set(), forced_modules=forced_modules)

    workspace = ensure_out_dir(out_dir)
    emitted = [emit_stub_library(workspace, module.name) for module in selected]
    unresolved = sorted(str(symbol) for symbol in manifest.get("required_symbols", []))

    write_manifest(
        workspace / "manifest.json",
        project=project,
        libraries=libraries,
        modules=selected,
        emitted=emitted,
        unresolved=unresolved,
    )
    write_report(
        workspace / "report.txt",
        [
            "conversion staged",
            f"project={project}",
            f"libraries={len(libraries)}",
            f"selected_modules={len(selected)}",
            f"emitted_artifacts={len(emitted)}",
        ],
    )

    return {
        "project": project,
        "libraries": libraries,
        "selected_modules": [module.name for module in selected],
        "emitted_artifacts": emitted,
        "unresolved_symbols": unresolved,
    }


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
        payload = convert_project(args.manifest, args.out_dir)
        print(json.dumps(payload, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
