"""Configuration: per-signal on/off, weight overrides, and the flag threshold.

Parsed from TOML via the stdlib ``tomllib`` - no third-party dependency. The
default config keeps the distinctive LLM tells plus the keyboard-character
folklore (em-dash, emoji - additive-only, D-12) and disables the prose-style
folklore (high human overlap); everything is overridable. Example::

    threshold = 40

    [signals]
    promotional_adjectives = true   # opt a prose-folklore signal in
    emoji_density = false           # opt a default signal out

    [weights]
    ai_self_reference = 6.0
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field

from slopscore.signals import SIGNALS
from slopscore.triage import DEFAULT_THRESHOLD

_NAMES = frozenset(s.name for s in SIGNALS)


def _default_enabled() -> frozenset[str]:
    return frozenset(s.name for s in SIGNALS if s.default_enabled)


@dataclass(frozen=True)
class Config:
    threshold: float = DEFAULT_THRESHOLD
    enabled: frozenset[str] = field(default_factory=_default_enabled)
    weights: dict[str, float] = field(default_factory=dict)


def default_config() -> Config:
    """The product default: distinctive tells + keyboard-character folklore
    on (the latter additive-only); prose-style folklore off (D-12)."""
    return Config()


def _check_name(name: str) -> None:
    if name not in _NAMES:
        raise ValueError(f"unknown signal in config: {name!r}")


def load_config(text: str) -> Config:
    """Parse a TOML config, layered over the defaults. Raises ValueError on bad
    TOML or an unknown signal name."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"invalid TOML: {exc}") from exc

    enabled = set(_default_enabled())
    for name, on in data.get("signals", {}).items():
        _check_name(name)
        enabled.add(name) if on else enabled.discard(name)

    weights: dict[str, float] = {}
    for name, weight in data.get("weights", {}).items():
        _check_name(name)
        value = float(weight)
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"weight for {name!r} must be a finite number >= 0")
        weights[name] = value

    threshold = float(data.get("threshold", DEFAULT_THRESHOLD))
    if not math.isfinite(threshold):
        raise ValueError("threshold must be a finite number")
    return Config(threshold=threshold, enabled=frozenset(enabled), weights=weights)
