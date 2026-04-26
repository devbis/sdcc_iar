from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


def _identifier(name: str) -> str:
    ident = re.sub(r"[^0-9A-Za-z_]", "_", name)
    if ident and ident[0].isdigit():
        ident = f"m_{ident}"
    return ident or "iar2sdcc_stub"


def _default_sdcc_bin() -> Path:
    return Path(__file__).resolve().parents[3] / "sdcc-build" / "bin" / "sdcc"


def emit_stub_library(out_dir: Path, module_name: str) -> str:
    symbol = _identifier(module_name)
    source = out_dir / f"{module_name}.stub.c"
    artifact = out_dir / f"{module_name}.stub.rel"
    source.write_text(f"void __iar2sdcc_{symbol}(void) {{}}\n", encoding="utf-8")

    sdcc_bin = Path(os.environ.get("IAR2SDCC_SDCC_BIN", _default_sdcc_bin()))
    if not sdcc_bin.exists():
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

    cmd = [str(sdcc_bin), "-mmcs51", f"--model-{os.environ.get('IAR2SDCC_SDCC_MODEL', 'large')}"]
    if os.environ.get("IAR2SDCC_SDCC_ABI", "") == "iar":
        cmd.append("--abi-iar")
    cmd.extend(["-c", "-o", str(artifact), str(source)])
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return str(artifact)
