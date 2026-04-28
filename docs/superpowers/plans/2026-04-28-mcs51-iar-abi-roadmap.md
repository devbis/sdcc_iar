# mcs51 IAR ABI Roadmap

## Goal

Reduce Z-Stack-specific source overlays by moving IAR compatibility into SDCC itself, then make SDCC-generated `mcs51` objects linkable against converted IAR libraries under one ABI model.

## Current State

SDCC already contains partial `mcs51` IAR ABI support:

- `--abi-iar` option in `src/mcs51/main.c`
- IAR ABI return / argument logic in `src/mcs51/gen.c`
- `__SDCC_mcs51_ABI_IAR` predefine in `src/SDCCmain.c`

This is still incomplete for Z-Stack-class firmware because source compatibility and ABI coverage are both partial.

## Completed In This Step

1. Add IAR qualifier aliases when `mcs51 --abi-iar` is active:
   - `__root`
   - `__near_func`
   - `__no_init`
   - `__intrinsic`
2. Add a raw `mcs51` pragma hook for safe IAR no-op pragmas:
   - `#pragma language=extended`
   - `#pragma language=default`
   - `#pragma optimize=none`
   - `#pragma optimize=low|medium|high|size|speed`

These changes are intentionally small and safe. They do not claim support for placement pragmas yet.

## Next Priority Work

1. Implement real `#pragma location=...` support for `mcs51`.
   - Needs "applies to next declaration" state.
   - Must distinguish:
     - named code/data segments
     - absolute placement
     - startup / reserved flash marker use-cases

2. Implement `#pragma required=symbol`.
   - Needed for linker retention of unreferenced reserved objects such as CRC / lockbits / NV markers.

3. Extend `--abi-iar` backend coverage in `src/mcs51/gen.c` and `src/mcs51/ralloc.c`.
   - bit parameters
   - aggregate parameters larger than 1 byte
   - hidden structure return pointer
   - function-pointer calls
   - varargs policy
   - caller/callee-saved behavior audit

4. Add `mcs51 --abi-iar` regression coverage.
   - compile-only source-compatibility tests
   - ABI tests for:
     - 1/2/3/4-byte returns
     - struct returns
     - callbacks
     - reentrant / nonbanked / interrupt combinations

5. Only after ABI is stable:
   - improve `tools/iar2sdcc`
   - optionally add direct IAR archive/object ingestion in SDCC binutils

## Why This Order

Direct `.lib` support is not sufficient if the generated caller/callee ABI is still mismatched.

The safest path is:

1. source compatibility
2. ABI compatibility
3. object/archive compatibility

That order gives usable progress for Z-Stack while keeping failures diagnosable.
