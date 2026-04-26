from __future__ import annotations

from pathlib import Path

from .archive import extract_module_spans
from .object_parser import parse_module_summary
from .report import write_json


def _library_dirname(library: str) -> str:
    stem = Path(library).stem
    return stem.replace(".lib", "")


def export_module_slices(
    out_dir: Path,
    module_plan: dict[str, list[dict[str, object]]],
) -> dict[str, list[dict[str, object]]]:
    exported: dict[str, list[dict[str, object]]] = {}
    for library, plan_entries in module_plan.items():
        data = Path(library).read_bytes()
        spans = {span.name: span for span in extract_module_spans(data)}
        library_dir = out_dir / "module-slices" / _library_dirname(library)
        entries: list[dict[str, object]] = []
        for plan_entry in plan_entries:
            module = plan_entry["module"]
            span = spans.get(module)
            if span is None:
                continue
            artifact = library_dir / f"{module}.bin"
            summary_path = artifact.with_suffix(".json")
            ir_path = artifact.with_name(f"{artifact.stem}.ir.json")
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(data[span.start_offset:span.end_offset])
            summary = parse_module_summary(artifact)
            write_json(summary_path, summary.to_dict())
            write_json(ir_path, summary.normalized_ir)
            entries.append(
                {
                    "module": module,
                    "path": str(artifact),
                    "summary_path": str(summary_path),
                    "ir_path": str(ir_path),
                    "start_offset": span.start_offset,
                    "end_offset": span.end_offset,
                    "size": span.size,
                    "symbols": plan_entry["symbols"],
                }
            )
        exported[library] = entries
    return exported
