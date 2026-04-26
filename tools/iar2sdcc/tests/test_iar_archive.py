import json
import subprocess
import sys
import unittest
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[4]
TOOLS = WORKSPACE / "sdcc" / "tools"
LIB = WORKSPACE / "Z-Stack_3.0.2" / "Projects" / "zstack" / "Libraries" / "TI2530DB" / "bin" / "Router-Pro.lib"
SECURITY_LIB = WORKSPACE / "Z-Stack_3.0.2" / "Projects" / "zstack" / "Libraries" / "TI2530DB" / "bin" / "Security.lib"
TIMAC_LIB = WORKSPACE / "Z-Stack_3.0.2" / "Projects" / "zstack" / "Libraries" / "TIMAC" / "bin" / "TIMAC-CC2530.lib"


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
        self.assertIn("symbols", payload)
        self.assertIn("_NLME_GetExtAddr", payload["symbols"])

    def test_resolve_matches_symbols_to_libraries(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "iar2sdcc.cli",
                "resolve",
                "--json",
                str(LIB),
                str(SECURITY_LIB),
                str(TIMAC_LIB),
                "_NLME_GetExtAddr",
                "_HalAesInit",
                "_MAC_CbackEvent",
            ],
            cwd=TOOLS,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(
            payload["_NLME_GetExtAddr"],
            [str(LIB.resolve())],
        )
        self.assertEqual(
            payload["_HalAesInit"],
            [str(SECURITY_LIB.resolve())],
        )
        self.assertEqual(
            payload["_MAC_CbackEvent"],
            [str(TIMAC_LIB.resolve())],
        )
