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

    def test_convert_with_link_log_emits_resolution_summary(self) -> None:
        log_text = """\
?ASlink-Warning-Undefined Global _APSME_GetRequest referenced by module ZDApp
?ASlink-Warning-Undefined Global _HalAesInit referenced by module ZDSecMgr
?ASlink-Warning-Undefined Global _MAC_MlmeOrphanRsp referenced by module zmac
"""
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "samplelight.link.log"
            log_path.write_text(log_text, encoding="utf-8")
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
                    "--link-log",
                    str(log_path),
                ],
                cwd=TOOLS,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads((Path(td) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["link_resolution"]["log"], str(log_path.resolve()))
            self.assertEqual(
                payload["link_resolution"]["libraries"]["_HalAesInit"],
                [
                    str(
                        (
                            WORKSPACE
                            / "Z-Stack_3.0.2"
                            / "Projects"
                            / "zstack"
                            / "Libraries"
                            / "TI2530DB"
                            / "bin"
                            / "Security.lib"
                        ).resolve()
                    )
                ],
            )
            report = (Path(td) / "report.txt").read_text(encoding="utf-8")
            self.assertIn("link_undefined_symbols=3", report)
            self.assertIn("link_symbols_without_owner=0", report)
