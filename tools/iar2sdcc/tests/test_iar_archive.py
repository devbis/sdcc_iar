import json
import subprocess
import sys
import tempfile
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
        self.assertIn("modules", payload)
        self.assertIn("_NLME_GetExtAddr", payload["symbols"])
        self.assertIn("AddrMgr", payload["modules"])
        self.assertIn("aps_groups", payload["modules"])

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

    def test_resolve_log_maps_undefined_symbols_to_libraries(self) -> None:
        log_text = """\
?ASlink-Warning-Undefined Global _NLME_GetExtAddr referenced by module zcl_samplelight
?ASlink-Warning-Undefined Global _HalAesInit referenced by module zmain
?ASlink-Warning-Undefined Global _MAC_CbackEvent referenced by module mac_task
?ASlink-Warning-Undefined Global _HalAesInit referenced by module zsec_mgr
?ASlink-Error-Insufficient ROM/EPROM/FLASH memory.
"""
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "samplelight.link.log"
            log_path.write_text(log_text, encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "iar2sdcc.cli",
                    "resolve-log",
                    "--json",
                    str(log_path),
                    str(LIB),
                    str(SECURITY_LIB),
                    str(TIMAC_LIB),
                ],
                cwd=TOOLS,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["log"], str(log_path.resolve()))
            self.assertEqual(
                payload["undefined_symbols"],
                ["_HalAesInit", "_MAC_CbackEvent", "_NLME_GetExtAddr"],
            )
            self.assertEqual(
                payload["references"]["_HalAesInit"],
                ["zmain", "zsec_mgr"],
            )
            self.assertEqual(
                payload["libraries"]["_NLME_GetExtAddr"],
                [str(LIB.resolve())],
            )
            self.assertEqual(
                payload["libraries"]["_HalAesInit"],
                [str(SECURITY_LIB.resolve())],
            )
            self.assertEqual(
                payload["libraries"]["_MAC_CbackEvent"],
                [str(TIMAC_LIB.resolve())],
            )
