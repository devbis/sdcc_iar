from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
import json


def _identifier(name: str) -> str:
    ident = re.sub(r"[^0-9A-Za-z_]", "_", name)
    if ident and ident[0].isdigit():
        ident = f"m_{ident}"
    return ident or "iar2sdcc_stub"


def _default_sdcc_bin() -> Path:
    return Path(__file__).resolve().parents[3] / "sdcc-build" / "bin" / "sdcc"


def _default_sdas_bin() -> Path:
    return Path(__file__).resolve().parents[3] / "sdcc-build" / "bin" / "sdas8051"


def _sdcc_base_cmd() -> list[str]:
    cmd = [str(Path(os.environ.get("IAR2SDCC_SDCC_BIN", _default_sdcc_bin())))]
    cmd.extend(["-mmcs51", f"--model-{os.environ.get('IAR2SDCC_SDCC_MODEL', 'large')}"])
    if os.environ.get("IAR2SDCC_SDCC_ABI", "") == "iar":
        cmd.append("--abi-iar")
    return cmd


def _compile_source(source: Path, artifact: Path) -> str:
    sdcc_bin = Path(os.environ.get("IAR2SDCC_SDCC_BIN", _default_sdcc_bin()))
    if not sdcc_bin.exists():
        artifact.write_text(
            "\n".join(
                [
                    "; temporary converter milestone artifact",
                    f"; source={source.name}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return str(artifact)

    cmd = _sdcc_base_cmd()
    cmd.extend(["-c", "-o", str(artifact), str(source)])
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return str(artifact)


def _assemble_source(source: Path, artifact: Path) -> str:
    sdas_bin = Path(os.environ.get("IAR2SDCC_SDAS_BIN", _default_sdas_bin()))
    if not sdas_bin.exists():
        artifact.write_text(
            "\n".join(
                [
                    "; temporary converter milestone artifact",
                    f"; source={source.name}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return str(artifact)

    cmd = [str(sdas_bin), "-los", str(artifact), str(source)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return str(artifact)


def emit_stub_library(out_dir: Path, module_name: str) -> str:
    symbol = _identifier(module_name)
    source = out_dir / f"{module_name}.stub.c"
    artifact = out_dir / f"{module_name}.stub.rel"
    source.write_text(f"void __iar2sdcc_{symbol}(void) {{}}\n", encoding="utf-8")
    return _compile_source(source, artifact)


def _is_data_symbol(symbol: str, normalized_ir: dict[str, object]) -> bool:
    if symbol in normalized_ir.get("data_symbols", []):
        return True
    if "_PARM_" in symbol or symbol.startswith("__"):
        return True
    if symbol.endswith(("TaskID", "Counter", "Rate", "Duration")):
        return True
    if symbol.startswith(("_AIB_", "_NIB", "_p")):
        return True
    return False


def _emit_exact_stub_module(
    source: Path,
    artifact: Path,
    module_name: str,
    functions: list[str],
    data_symbols: list[str],
) -> str:
    lines = [f"; auto-stub for {module_name}", f"\t.module {_identifier(module_name)}"]
    for symbol in functions:
        lines.append(f"\t.globl {symbol}")
    for symbol in data_symbols:
        lines.append(f"\t.globl {symbol}")

    lines.append("\t.area XSEG    (XDATA)")
    for symbol in data_symbols:
        lines.append(f"{symbol}::")
        lines.append("\t.ds 1")

    lines.append("\t.area CSEG    (CODE)")
    for symbol in functions:
        lines.append(f"{symbol}::")
        lines.append("\tret")

    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return _assemble_source(source, artifact)


def emit_auto_stub_module(
    out_dir: Path,
    module_name: str,
    symbols: list[str],
    normalized_ir: dict[str, object],
) -> str:
    source = out_dir / f"{module_name}.auto.asm"
    artifact = out_dir / f"{module_name}.auto.rel"
    callable_symbols = set(normalized_ir.get("public_callables", [])) | set(
        normalized_ir.get("internal_callables", [])
    )

    functions: list[str] = []
    data_symbols: list[str] = []
    emitted: set[str] = set()
    for symbol in symbols:
        if symbol in emitted:
            continue
        emitted.add(symbol)
        if symbol in callable_symbols or not _is_data_symbol(symbol, normalized_ir):
            functions.append(symbol)
        else:
            data_symbols.append(symbol)
    return _emit_exact_stub_module(source, artifact, module_name, functions, data_symbols)


def emit_fallback_stub(out_dir: Path, module_name: str, symbols: list[str]) -> str:
    source = out_dir / f"{module_name}.auto.asm"
    artifact = out_dir / f"{module_name}.auto.rel"
    functions: list[str] = []
    data_symbols: list[str] = []
    for symbol in sorted(set(symbols)):
        if _is_data_symbol(symbol, {}):
            data_symbols.append(symbol)
        else:
            functions.append(symbol)
    return _emit_exact_stub_module(
        source,
        artifact,
        module_name,
        functions,
        data_symbols,
    )


def emit_ownerless_stub(out_dir: Path, symbols: list[str]) -> str:
    return emit_fallback_stub(out_dir, "ownerless", symbols)
