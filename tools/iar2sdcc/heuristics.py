from __future__ import annotations

import re


UPPER_REGISTER_RE = re.compile(r"^_[A-Z][A-Z0-9_]*[0-9][A-Z0-9_]*$")


def is_type_symbol(symbol: str) -> bool:
    return symbol.lstrip("_").endswith("_t")


def is_register_noise_symbol(symbol: str) -> bool:
    return bool(UPPER_REGISTER_RE.match(symbol))


def is_noise_symbol(symbol: str) -> bool:
    return is_type_symbol(symbol) or is_register_noise_symbol(symbol)
