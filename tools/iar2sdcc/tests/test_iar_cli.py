import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[4]
TOOLS = WORKSPACE / "sdcc" / "tools"
MANIFEST = WORKSPACE / "Z-Stack_3.0.2" / "Tools" / "sdcc" / "manifests" / "samplelight-cc2530db-coordinator.json"


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
        self.assertIn("resolve-log", proc.stdout)
        self.assertIn("convert", proc.stdout)


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
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            self.assertTrue((Path(td) / "manifest.json").exists())
            self.assertTrue((Path(td) / "report.txt").exists())
            payload = json.loads((Path(td) / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("project", payload)
