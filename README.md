# SDCC for Z-Stack 3.0.2

This tree contains SDCC changes and helper tooling needed to build a `Z-Stack_3.0.2` firmware image for `cc2530` without invoking IAR build tools.

The current supported flow is:

1. build this `sdcc` tree into a sibling build directory;
2. keep `Z-Stack_3.0.2` next to the `sdcc` checkout;
3. use the helper scripts in `Z-Stack_3.0.2/Tools/sdcc/`;
4. generate the final `ihx` and `hex` with SDCC tools only.

## Workspace layout

The scripts assume this layout:

```text
<workspace>/
  sdcc/
  sdcc-build/
  Z-Stack_3.0.2/
```

`sdcc-build` is an out-of-tree build directory for this repository. `Z-Stack_3.0.2` is the Zigbee SDK tree that contains the application sources, manifests, and helper wrappers.

## Prerequisites

You need a normal SDCC build environment plus a few scripting tools used by the Z-Stack wrappers:

- `autoconf`
- `automake`
- `make`
- `gcc` and `g++`
- `bison`
- `flex`
- `python3`
- `jq`

## Build SDCC

From the workspace root:

```bash
mkdir -p sdcc-build
cd sdcc-build
../sdcc/configure --disable-sdcdb --disable-sdbinutils --disable-ucsim
make -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 8)"
```

This produces the local toolchain used by the Z-Stack scripts:

- `sdcc-build/bin/sdcc`
- `sdcc-build/bin/sdld`
- `sdcc-build/bin/packihx`

No IAR binaries are required for the firmware build itself.

## Z-Stack Build Flow

The current integration targets the `SampleLight` `CoordinatorEB` configuration for `CC2530DB`.

The flow is manifest-driven:

- the IAR project is first exported into a JSON manifest and an SDCC preinclude header;
- the firmware sources are compiled with `sdcc -mmcs51 --abi-iar`;
- unresolved references to TI IAR libraries are analyzed with `tools/iar2sdcc`;
- replacement stub libraries and module slices are generated locally;
- final linking is done with `sdcc` and `sdld`, then `packihx` emits the final hex.

Important current behavior:

- the build wrappers intentionally avoid direct linkage against raw IAR `.lib` archives;
- the port includes `--abi-iar` support in the `mcs51` backend so SDCC-generated objects can match the calling convention expected by converted Z-Stack pieces;
- the helper scripts already know how to replace the two IAR-only assembler inputs that block a direct SDCC compile path.

## Build SampleLight

Run the main wrapper:

```bash
bash Z-Stack_3.0.2/Tools/sdcc/build_samplelight.sh \
  sdcc-build/zstack-samplelight-cc2530db-coordinator
```

Expected outputs:

- `sdcc-build/zstack-samplelight-cc2530db-coordinator/samplelight-cc2530db-coordinator.ihx`
- `sdcc-build/zstack-samplelight-cc2530db-coordinator/samplelight-cc2530db-coordinator.hex`

The wrapper also emits intermediate diagnostics such as:

- `link.log`
- `first-pass.link.log`
- `second-pass-strict.link.log`
- `manifest.json`
- `module-plan.json`
- `report.txt`

These files are useful when the converted library plan still misses symbols.

## Build the F256 Hex Variant

To build the reduced `CC2530F256` coordinator image:

```bash
bash Z-Stack_3.0.2/Tools/sdcc/build_samplelight_cc2530f256_hex.sh \
  sdcc-build/zstack-samplelight-cc2530db-coordinator-stackauto-f256-hex
```

This wrapper derives a reduced manifest and then runs the normal SDCC flow with stricter flash validation for the final image.

## Useful Knobs

The Z-Stack build wrappers accept environment overrides:

- `SDCC_MODEL=large` or `SDCC_MODEL=huge`
- `SDCC_ABI=iar`
- `SDCC_STACK_MODE=default`
- `SDCC_STACK_MODE=stack-auto`
- `SDCC_STACK_MODE=stack-auto-xstack`
- `SDCC_CODE_SIZE=<hex>`
- `SDCC_XRAM_LOC=<hex>`
- `SDCC_XRAM_SIZE=<hex>`
- `SDCC_XSTACK_LOC=<hex>`
- `SDCC_EXTRA_ARGS='<extra sdcc flags>'`
- `CONVERTED_DIR=<path>`
- `RELAX_MEMORY=0` or `RELAX_MEMORY=1`

Example:

```bash
SDCC_STACK_MODE=stack-auto \
SDCC_CODE_SIZE=0x40000 \
RELAX_MEMORY=0 \
bash Z-Stack_3.0.2/Tools/sdcc/build_samplelight_cc2530f256_hex.sh \
  sdcc-build/zstack-samplelight-f256
```

## Extract or Refresh the Manifest

If the IAR project changes, refresh the manifest and SDCC config header with:

```bash
python3 Z-Stack_3.0.2/Tools/sdcc/extract_iar_project.py \
  Z-Stack_3.0.2/Projects/zstack/HomeAutomation/SampleLight/CC2530DB/SampleLight.ewp \
  --config CoordinatorEB \
  --output Z-Stack_3.0.2/Tools/sdcc/manifests/samplelight-cc2530db-coordinator.json \
  --sdcc-header-output Z-Stack_3.0.2/Tools/sdcc/manifests/samplelight-cc2530db-coordinator-sdcc-cfg.h
```

This step reads project metadata only. It does not invoke the IAR compiler or linker.

## Inspect or Rebuild the IAR Conversion Plan

Inspect one or more IAR libraries:

```bash
python3 sdcc/tools/iar2sdcc/cli.py scan \
  Z-Stack_3.0.2/Projects/zstack/Libraries/TI2530DB/bin/Router-Pro.lib
```

Generate or refresh converted artifacts for the current manifest:

```bash
python3 sdcc/tools/iar2sdcc/cli.py convert \
  --manifest Z-Stack_3.0.2/Tools/sdcc/manifests/samplelight-cc2530db-coordinator.json \
  --out-dir sdcc-build/iar-converted/samplelight-cc2530db-coordinator
```

If you already have a link log from a failing build, feed it back into the converter:

```bash
python3 sdcc/tools/iar2sdcc/cli.py convert \
  --manifest Z-Stack_3.0.2/Tools/sdcc/manifests/samplelight-cc2530db-coordinator.json \
  --out-dir sdcc-build/iar-converted/samplelight-cc2530db-coordinator \
  --link-log sdcc-build/zstack-samplelight-cc2530db-coordinator/link.log
```

## Notes

- The root `README` file was replaced by this Markdown document on purpose.
- The old generic pointer to `doc/README.txt` is no longer the most useful entry point for this fork.
- Upstream SDCC reference material is still available under `doc/`.
