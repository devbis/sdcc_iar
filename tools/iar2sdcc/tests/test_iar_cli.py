import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from iar2sdcc.archive import scan_library


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
        self.assertIn("inspect-slice", proc.stdout)
        self.assertIn("scan", proc.stdout)
        self.assertIn("resolve-log", proc.stdout)
        self.assertIn("convert", proc.stdout)


class ArchiveScanTest(unittest.TestCase):
    def test_scan_library_detects_short_router_modules(self) -> None:
        inventory = scan_library(
            (
                WORKSPACE
                / "Z-Stack_3.0.2"
                / "Projects"
                / "zstack"
                / "Libraries"
                / "TI2530DB"
                / "bin"
                / "Router-Pro.lib"
            )
        )
        self.assertIn("APS", inventory.modules)
        self.assertIn("nwk", inventory.modules)
        self.assertIn("rtg", inventory.modules)
        self.assertIn("ssp", inventory.modules)


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
                payload["unresolved_symbols"],
                [
                    "_APSME_GetRequest",
                    "_HalAesInit",
                    "_MAC_MlmeOrphanRsp",
                ],
            )
            self.assertIn("manifest_required_symbols", payload)
            module_plan_file = Path(td) / "module-plan.json"
            self.assertTrue(module_plan_file.exists())
            plan_payload = json.loads(module_plan_file.read_text(encoding="utf-8"))
            module_slice_file = Path(td) / "module-slices" / "Security" / "hal_aes.bin"
            module_slice_summary = Path(td) / "module-slices" / "Security" / "hal_aes.json"
            module_slice_ir = Path(td) / "module-slices" / "Security" / "hal_aes.ir.json"
            auto_stub_asm = Path(td) / "hal_aes.auto.asm"
            self.assertTrue(module_slice_file.exists())
            self.assertTrue(module_slice_summary.exists())
            self.assertTrue(module_slice_ir.exists())
            self.assertTrue(auto_stub_asm.exists())
            self.assertEqual(
                plan_payload["project"],
                "samplelight-cc2530db-coordinator",
            )
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
            self.assertTrue(
                any(path.endswith(".auto.rel") for path in payload["emitted_artifacts"])
            )
            self.assertIn(
                "APSMEDE",
                payload["link_resolution"]["module_candidates"]["_APSME_GetRequest"][
                    str(
                        (
                            WORKSPACE
                            / "Z-Stack_3.0.2"
                            / "Projects"
                            / "zstack"
                            / "Libraries"
                            / "TI2530DB"
                            / "bin"
                            / "Router-Pro.lib"
                        ).resolve()
                    )
                ],
            )
            self.assertIn(
                "hal_aes",
                payload["link_resolution"]["module_candidates"]["_HalAesInit"][
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
            security_lib = str(
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
            router_lib = str(
                (
                    WORKSPACE
                    / "Z-Stack_3.0.2"
                    / "Projects"
                    / "zstack"
                    / "Libraries"
                    / "TI2530DB"
                    / "bin"
                    / "Router-Pro.lib"
                ).resolve()
            )
            self.assertEqual(
                payload["link_resolution"]["module_plan"][security_lib][0]["module"],
                "hal_aes",
            )
            self.assertEqual(
                payload["link_resolution"]["module_plan"][security_lib][0]["symbols"],
                ["_HalAesInit"],
            )
            self.assertEqual(
                payload["link_resolution"]["module_plan"][router_lib][0]["module"],
                "APSMEDE",
            )
            self.assertEqual(
                plan_payload["module_plan"],
                payload["link_resolution"]["module_plan"],
            )
            summary_payload = json.loads(module_slice_summary.read_text(encoding="utf-8"))
            ir_payload = json.loads(module_slice_ir.read_text(encoding="utf-8"))
            self.assertEqual(summary_payload["module"], "hal_aes")
            self.assertEqual(summary_payload["code_model"], "banked")
            self.assertEqual(summary_payload["data_model"], "large")
            self.assertIn("_HalAesInit", summary_payload["symbols"])
            self.assertEqual(ir_payload["module"], "hal_aes")
            self.assertIn("_HalAesInit", ir_payload["public_callables"])
            auto_stub_text = auto_stub_asm.read_text(encoding="utf-8")
            self.assertIn(".globl _HalAesInit", auto_stub_text)
            self.assertNotIn(".globl __HalAesInit", auto_stub_text)
            self.assertTrue(
                any(
                    entry["module"] == "hal_aes"
                    for entry in plan_payload["module_slices"][security_lib]
                )
            )
            report = (Path(td) / "report.txt").read_text(encoding="utf-8")
            self.assertIn("link_undefined_symbols=3", report)
            self.assertIn("link_symbols_without_owner=0", report)
            self.assertIn("link_symbols_with_module_candidates=3", report)
            self.assertIn("link_planned_modules=3", report)
            self.assertIn("link_exported_module_slices=3", report)

    def test_inspect_slice_reads_exported_module_summary(self) -> None:
        log_text = """\
?ASlink-Warning-Undefined Global _HalAesInit referenced by module ZDSecMgr
"""
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "samplelight.link.log"
            log_path.write_text(log_text, encoding="utf-8")
            convert = subprocess.run(
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
            self.assertEqual(convert.returncode, 0, msg=convert.stderr)
            slice_path = Path(td) / "module-slices" / "Security" / "hal_aes.bin"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "iar2sdcc.cli",
                    "inspect-slice",
                    "--json",
                    str(slice_path),
                ],
                cwd=TOOLS,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["module"], "hal_aes")
            self.assertEqual(payload["calling_convention"], "xdata_reentrant")
            self.assertEqual(payload["code_model"], "banked")
            self.assertIn("_HalAesInit", payload["symbols"])
            self.assertIn("_HalAesInit", payload["exports"])
            self.assertIn("_osal_memcpy", payload["imports"])
            self.assertIn("_Jf1g", payload["noise_symbols"])
            self.assertIn("_HalAesInit", payload["normalized_ir"]["public_exports"])
            self.assertIn("_SSP_CCM_Encrypt", payload["normalized_ir"]["public_exports"])
            self.assertIn("_AesLoadIV", payload["normalized_ir"]["internal_exports"])
            self.assertIn("_sspAesEncryptHW", payload["normalized_ir"]["internal_exports"])
            self.assertIn("_osal_memcpy", payload["normalized_ir"]["required_imports"])
            self.assertIn("_HalAesInit", payload["normalized_ir"]["public_callables"])
            self.assertIn("_sspAesEncryptHW", payload["normalized_ir"]["internal_callables"])
            self.assertIn("_dmaCh1234", payload["normalized_ir"]["data_symbols"])
