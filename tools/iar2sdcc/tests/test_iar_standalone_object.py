import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from iar2sdcc.object_parser import classify_symbols, parse_iar_object


WORKSPACE = Path(__file__).resolve().parents[4]
TOOLS = WORKSPACE / "sdcc" / "tools"
ECC_R51 = (
    WORKSPACE
    / "Z-Stack_3.0.2"
    / "Projects"
    / "zstack"
    / "Libraries"
    / "TI2530DB"
    / "bin"
    / "ecc.r51"
)
BASE_MANIFEST = (
    WORKSPACE
    / "Z-Stack_3.0.2"
    / "Tools"
    / "sdcc"
    / "manifests"
    / "samplelight-cc2530db-coordinator.json"
)


class StandaloneObjectParserTest(unittest.TestCase):
    def test_parse_iar_object_extracts_models_symbols_and_sections(self) -> None:
        obj = parse_iar_object(ECC_R51)

        self.assertEqual(obj.module, "eccapi")
        self.assertEqual(obj.code_model, "banked")
        self.assertEqual(obj.data_model, "large")
        self.assertTrue(any(sym.name == "_ZSE_ECCGenerateKey" for sym in obj.symbols))
        self.assertTrue(any(sec.kind == "code" for sec in obj.sections))
        self.assertTrue(obj.relocations)

    def test_classify_symbols_filters_type_and_field_markers_from_imports(self) -> None:
        exports, imports, noise, unknown = classify_symbols(
            "mac_beacon",
            "xdata_reentrant",
            [
                "_MAC_Init",
                "_macEventLoop",
                "_osal_memcpy",
                "_sAddrExtCmp",
                "_sAddr_t",
                "_osal_msg_q_t",
                "_A_IEN0",
                "_AckBits",
                "_ProfileID",
                "_ReflectTracking_t",
            ],
        )

        self.assertIn("_MAC_Init", exports)
        self.assertIn("_macEventLoop", exports)
        self.assertIn("_osal_memcpy", imports)
        self.assertIn("_sAddrExtCmp", imports)
        self.assertIn("_sAddr_t", noise)
        self.assertIn("_osal_msg_q_t", noise)
        self.assertIn("_ReflectTracking_t", noise)
        self.assertIn("_A_IEN0", noise)
        self.assertIn("_AckBits", unknown)
        self.assertIn("_ProfileID", unknown)


class StandaloneObjectConvertTest(unittest.TestCase):
    def test_convert_can_plan_module_from_single_r51_object(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "ecc-manifest.json"
            link_log_path = Path(td) / "ecc.link.log"
            manifest = json.loads(BASE_MANIFEST.read_text(encoding="utf-8"))
            manifest["iar_libraries"] = [str(ECC_R51)]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            link_log_path.write_text(
                "?ASlink-Warning-Undefined Global _ZSE_ECCGenerateKey referenced by module test\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "iar2sdcc.cli",
                    "convert",
                    "--manifest",
                    str(manifest_path),
                    "--out-dir",
                    td,
                    "--link-log",
                    str(link_log_path),
                ],
                cwd=TOOLS,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)

            payload = json.loads((Path(td) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                payload["link_resolution"]["libraries"]["_ZSE_ECCGenerateKey"],
                [str(ECC_R51.resolve())],
            )
            self.assertEqual(
                payload["link_resolution"]["module_candidates"]["_ZSE_ECCGenerateKey"][
                    str(ECC_R51.resolve())
                ],
                ["eccapi"],
            )
            self.assertEqual(
                payload["link_resolution"]["module_plan"][str(ECC_R51.resolve())][0]["module"],
                "eccapi",
            )


class StandaloneObjectRealConvertTest(unittest.TestCase):
    def test_convert_object_emits_rel_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "iar2sdcc.cli",
                    "convert-object",
                    str(ECC_R51),
                    "--out-dir",
                    td,
                ],
                cwd=TOOLS,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)

            payload = json.loads(proc.stdout)
            rel_path = Path(payload["rel_path"])
            metadata_path = Path(payload["metadata_path"])
            manifest_path = Path(td) / "manifest.json"

            self.assertEqual(payload["module"], "eccapi")
            self.assertTrue(rel_path.exists())
            self.assertTrue(metadata_path.exists())
            self.assertTrue(manifest_path.exists())

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["module"], "eccapi")
            self.assertEqual(metadata["code_model"], "banked")
            self.assertEqual(metadata["data_model"], "large")
            self.assertIn("_ZSE_ECCGenerateKey", metadata["exports"])
            self.assertEqual(metadata["conversion_mode"], "banked_prototype_asm")
            self.assertEqual(metadata["area_plan"]["function_area"]["name"], "BANKED_CODE")
            self.assertIn("BANKED_CODE", metadata["area_plan"]["banked_code_areas"])

            asm_text = rel_path.with_suffix(".converted.asm").read_text(encoding="utf-8")
            self.assertIn(".area BANKED_CODE", asm_text)

    def test_convert_object_preserves_named_iar_layout_areas(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "iar2sdcc.cli",
                    "convert-object",
                    str(ECC_R51),
                    "--out-dir",
                    td,
                ],
                cwd=TOOLS,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)

            payload = json.loads(proc.stdout)
            metadata_path = Path(payload["metadata_path"])
            rel_path = Path(payload["rel_path"])
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

            self.assertEqual(
                metadata["area_plan"]["section_area_map"]["BANK_RELAYS"]["role"],
                "bank_relays",
            )
            self.assertIn("BANK_RELAYS", metadata["area_plan"]["root_code_areas"])

            asm_text = rel_path.with_suffix(".converted.asm").read_text(encoding="utf-8")
            self.assertIn(".area BANK_RELAYS", asm_text)


if __name__ == "__main__":
    unittest.main()
