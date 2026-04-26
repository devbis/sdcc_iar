from __future__ import annotations

import re


CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[0-9]+")


def _split_parts(value: str) -> list[str]:
    parts: list[str] = []
    for chunk in value.replace("-", "_").split("_"):
        if not chunk:
            continue
        matches = CAMEL_RE.findall(chunk)
        if matches:
            parts.extend(part.lower() for part in matches)
            continue
        parts.append(chunk.lower())
    normalized: list[str] = []
    for part in parts:
        normalized.append(part)
        if len(part) > 3 and part.endswith("s"):
            normalized.append(part[:-1])
    return normalized


def _normalize_key(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _common_prefix_len(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def _score_module(symbol: str, module: str) -> int:
    symbol_name = symbol.lstrip("_")
    symbol_key = _normalize_key(symbol_name)
    module_key = _normalize_key(module)
    if not symbol_key or not module_key:
        return 0

    score = 0
    if symbol_key.startswith(module_key):
        score += 8
    if module_key in symbol_key:
        score += 5

    prefix_len = _common_prefix_len(symbol_key, module_key)
    if prefix_len >= 3:
        score += min(prefix_len, 6)

    symbol_parts = set(_split_parts(symbol_name))
    module_parts = set(_split_parts(module))
    overlap = symbol_parts.intersection(module_parts)
    score += len(overlap) * 3

    if symbol_parts and module_parts:
        symbol_first = next(iter(_split_parts(symbol_name)), "")
        module_first = next(iter(_split_parts(module)), "")
        if symbol_first and symbol_first == module_first:
            score += 3

    return score


def candidate_modules_for_symbol(
    symbol: str,
    modules: list[str],
    *,
    limit: int = 5,
) -> list[str]:
    scored = []
    for module in modules:
        score = _score_module(symbol, module)
        if score <= 0:
            continue
        scored.append((score, module))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [module for _, module in scored[:limit]]


def build_module_candidates(
    libraries: dict[str, list[str]],
    resolved_symbols: dict[str, list[str]],
) -> dict[str, dict[str, list[str]]]:
    candidates: dict[str, dict[str, list[str]]] = {}
    for symbol, owners in resolved_symbols.items():
        symbol_candidates: dict[str, list[str]] = {}
        for owner in owners:
            symbol_candidates[owner] = candidate_modules_for_symbol(
                symbol,
                libraries.get(owner, []),
            )
        candidates[symbol] = symbol_candidates
    return candidates


def build_module_plan(
    module_candidates: dict[str, dict[str, list[str]]],
) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, dict[str, list[str]]] = {}
    for symbol, library_candidates in module_candidates.items():
        for library, candidates in library_candidates.items():
            if not candidates:
                continue
            module = candidates[0]
            library_plan = grouped.setdefault(library, {})
            symbols = library_plan.setdefault(module, [])
            symbols.append(symbol)

    plan: dict[str, list[dict[str, object]]] = {}
    for library, modules in grouped.items():
        records = [
            {
                "module": module,
                "symbol_count": len(sorted(symbols)),
                "symbols": sorted(symbols),
            }
            for module, symbols in modules.items()
        ]
        records.sort(key=lambda record: (-record["symbol_count"], record["module"]))
        plan[library] = records
    return plan
