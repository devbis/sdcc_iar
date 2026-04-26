# Z-Stack 3.0.2 IAR Library Converter Design

Date: 2026-04-26

## Goal

Build a narrow, manifest-driven converter for the TI IAR 8051 libraries used by `Z-Stack_3.0.2`, so SDCC-based builds can replace direct linkage against IAR `.lib` archives with converted SDCC-consumable artifacts.

The first success target is not a final flashable `hex`. The first success target is:

- convert only the modules actually needed by the `samplelight-cc2530db-coordinator` build;
- emit converted artifacts plus a generated manifest/report;
- make `build_samplelight.sh` capable of consuming those converted artifacts instead of raw IAR libraries;
- leave remaining failures limited to known memory-fit or uncovered-library issues, not archive-format or ABI-mismatch issues.

## Scope

This converter is intentionally narrow.

Included:

- `Z-Stack_3.0.2`
- TI libraries currently referenced by the SampleLight manifest:
  - `Router-Pro.lib`
  - `Security.lib`
  - `TIMAC-CC2530.lib`
- a semi-automatic flow with project-specific overrides
- support only for the subset of IAR object/archive records actually present in these libraries

Excluded for the first iteration:

- general support for arbitrary IAR 8051 libraries
- direct IAR `.lib` support inside `sdcc` or `aslink`
- removal of all overrides
- final automatic handling of every banked edge case
- full memory-fit solution for CC2530

## Non-Goals

- Do not modify `aslink` to read IAR archives directly.
- Do not attempt a universal `IAR -> SDCC` converter.
- Do not attempt to solve all undefined Z-Stack symbols by handwritten stubs.
- Do not silently guess unsupported relocations or banked semantics.

## Why This Approach

Three architectural options were considered:

1. Add native IAR archive/object support to SDCC linker.
2. Run conversion lazily inside the SampleLight build script.
3. Build an offline, manifest-driven external converter with project-specific overrides.

Option 3 is recommended because it isolates the risky reverse-engineering work from the linker, keeps diagnostics explicit, and lets conversion progress incrementally without destabilizing the SDCC toolchain.

## High-Level Architecture

The converter lives under:

- `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/`

It is a standalone preprocessing stage that runs before the final SDCC link.

Inputs:

- TI IAR `.lib` files from `Z-Stack_3.0.2/Projects/zstack/Libraries/...`
- the project manifest already used by `build_samplelight.sh`
- a project-specific override file

Outputs:

- converted artifacts under `sdcc-build/iar-converted/<project>/`
- a generated manifest describing what was selected and emitted
- a report describing unresolved and unsupported cases

The build flow becomes:

1. compile Z-Stack sources with SDCC and `--abi-iar`
2. run library converter
3. link compiled objects against converted library artifacts plus SDCC runtime libraries

## Pipeline

### 1. Library Index Reader

Responsibility:

- open TI IAR `.lib`
- enumerate member modules
- extract archive-level symbol/member index
- expose raw module payloads for later parsing

Failure policy:

- unknown archive structure is fatal
- partial extraction is allowed only if the failing module is not selected later

### 2. Module Parser

Responsibility:

- parse the IAR object records of one library member
- decode sections, symbols, relocation entries, and model attributes
- identify banked markers and calling convention hints

Output:

- normalized in-memory `Module` representation

Failure policy:

- unrecognized record kinds become `unsupported`
- no best-effort guessing

### 3. Selector

Responsibility:

- determine which modules are needed for one concrete project build
- use undefined symbols from the project plus library exports
- apply include/exclude rules from overrides

Behavior:

- prefer the smallest sufficient module set
- keep the output deterministic

### 4. Normalizer

Responsibility:

- translate IAR-specific attributes into a converter IR
- classify relocations into:
  - directly translatable
  - translatable with override hint
  - unsupported
- mark banked callsites and symbols explicitly

### 5. Emitter

Responsibility:

- emit SDCC-consumable artifacts from the normalized module set
- emit a generated manifest describing those outputs

First-iteration constraint:

- the emitter only needs to support the subset required by the selected SampleLight modules
- unsupported constructs must remain explicit build errors

### 6. Reporter

Responsibility:

- produce machine-readable and human-readable diagnostics:
  - selected modules
  - emitted artifacts
  - unresolved symbols
  - unsupported relocation kinds
  - modules requiring manual overrides

## Internal Representation

The converter uses a narrow IR.

### Library

- source path
- module list
- global symbol index

### Module

- source library
- member name
- code/data model attributes
- banked flags
- sections
- symbols
- relocations
- conversion issues

### Section

- name
- logical kind: `code`, `const`, `data`, `idata`, `xdata`, `pdata`, `bit`
- alignment
- raw bytes

### Symbol

- name
- binding: local/global/import
- defining section
- offset
- attributes

### Relocation

- source section
- source offset
- relocation kind
- target symbol
- addend
- banked or model-specific flags

### ConversionIssue

- severity: `warning`, `needs_override`, `unsupported`
- module
- section/offset if relevant
- explanatory text

## Overrides

Overrides are project-specific and only describe exceptions from the automatic path.

Recommended path:

- `Z-Stack_3.0.2/Tools/sdcc/iar2sdcc/overrides/samplelight-cc2530db-coordinator.yaml`

Supported override intents:

- force-include a module
- force-exclude a module
- rename a symbol
- declare a symbol or module banked
- route an unsupported relocation through a known handling rule
- replace a module with a manual artifact or stub
- mark a module as `manual` so the converter stops with a precise message

The override file is part of the supported workflow, not a temporary hack.

## Generated Manifest

The converter writes a generated manifest into the conversion output directory.

It records:

- source libraries processed
- selected modules
- exports provided by each selected module
- unresolved imports after selection
- emitted artifact paths
- overrides applied
- unsupported or skipped items

This manifest becomes the stable handshake between the converter and `build_samplelight.sh`.

## Integration With `build_samplelight.sh`

`build_samplelight.sh` remains the top-level entrypoint for the SampleLight build.

Required changes:

- invoke the converter before final link
- use a project-specific conversion cache directory
- detect when conversion outputs are fresh enough to reuse
- link against converted artifacts first
- continue linking against SDCC runtime libraries after that
- fail early with a targeted conversion report if a required module cannot be converted

The script must not fall back to raw IAR `.lib` linkage.

## Output Layout

Recommended output tree:

- `sdcc-build/iar-converted/samplelight-cc2530db-coordinator/`

Contents:

- `manifest.json`
- `report.txt`
- converted objects or SDCC library artifacts
- intermediate parse dumps when debug mode is enabled

## Error Handling

The converter must be strict.

Rules:

- unsupported object records are explicit errors
- unsupported relocation kinds are explicit errors
- missing required exports are explicit errors
- override-requiring cases stop the build with a direct message pointing at the override file

The converter must never silently emit incomplete objects.

## Verification Strategy

Verification is staged.

### Stage 1: Reader Verification

- archive member listing matches current `inspect_iar_lib.py` observations
- exported symbols from parsed modules match inspection results for a sample set

### Stage 2: Parser Verification

- selected modules from each TI library can be parsed into IR without unknown records
- banked/model attributes extracted from parsed data match current manual inspection

### Stage 3: Emitter Verification

- emitted artifacts can be consumed by the SDCC toolchain
- linker no longer fails because raw IAR `.lib` is unreadable

### Stage 4: Build Verification

- `build_samplelight.sh` consumes converted artifacts
- prior ABI/runtime conflicts remain absent
- remaining build failures are limited to:
  - missing uncovered library semantics
  - known unresolved symbols from not-yet-converted modules
  - memory-fit limitations

## Key Risks

### IAR Object Format Complexity

The exact record formats, relocation encoding, and special linker metadata may be more complex than implied by current inspection tools.

Mitigation:

- implement only observed record kinds first
- keep unknown constructs fatal and visible

### Banked Call Semantics

The TI libraries are marked `banked`, `large`, and `xdata_reentrant`. Banked transitions may require more than straightforward symbol/section translation.

Mitigation:

- represent banked state explicitly in IR
- require override rules for cases that need hand-authored handling

### Emitter Scope Creep

A full universal SDCC `.rel` emitter would expand the project too much.

Mitigation:

- constrain the first emitter to the subset needed by SampleLight
- treat generalization as later work

### Memory Fit

Even with successful conversion, the final image may still exceed CC2530 RAM/ROM limits.

Mitigation:

- treat format conversion and memory-fit as separate tracks
- do not block converter success on final image fit

## Success Criteria

The first milestone is complete when all of the following are true:

- the converter reads the three TI libraries used by SampleLight
- the converter selects only the modules needed by the project
- converted artifacts are emitted into `sdcc-build/iar-converted/samplelight-cc2530db-coordinator/`
- `build_samplelight.sh` uses those converted artifacts instead of raw IAR `.lib`
- final build output no longer shows archive-format or ABI-runtime-mismatch failures
- any remaining failure is narrowed to memory-fit or uncovered-library semantics

## Follow-Up Work

After the narrow converter works:

1. reduce the number of manual overrides
2. widen record/relocation support
3. automate more banked handling
4. generalize from project-specific conversion to broader TI IAR library coverage
5. only then consider whether any SDCC/aslink integration is worth doing
