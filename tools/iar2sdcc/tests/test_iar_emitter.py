import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from iar2sdcc.models import ModuleRecord
from iar2sdcc.report import write_manifest


WORKSPACE = Path(__file__).resolve().parents[4]
TOOLS = WORKSPACE / "sdcc" / "tools"
MANIFEST = WORKSPACE / "Z-Stack_3.0.2" / "Tools" / "sdcc" / "manifests" / "samplelight-cc2530db-coordinator.json"


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


class ConvertArtifactTest(unittest.TestCase):
    def test_convert_emits_artifact_paths(self) -> None:
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
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads((Path(td) / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("emitted_artifacts", payload)
            self.assertTrue(payload["emitted_artifacts"])
