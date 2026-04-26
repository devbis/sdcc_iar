import json
import subprocess
import sys
import unittest
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[4]
TOOLS = WORKSPACE / "sdcc" / "tools"
LIB = WORKSPACE / "Z-Stack_3.0.2" / "Projects" / "zstack" / "Libraries" / "TI2530DB" / "bin" / "Router-Pro.lib"


class IarArchiveScanTest(unittest.TestCase):
    def test_scan_emits_json_inventory(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "iar2sdcc.cli", "scan", "--json", str(LIB)],
            cwd=TOOLS,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["library"], str(LIB.resolve()))
        self.assertIn("size", payload)
        self.assertIn("strings", payload)
        self.assertIn("banked_markers", payload)
