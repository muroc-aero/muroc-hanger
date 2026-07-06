"""phase_info construction and validation for Aviary missions.

Aviary missions are described by a plain-Python ``phase_info`` dict. This
module builds one from the upstream energy_state default plus declarative
overrides, validating every key the caller touches so typos fail loudly
here instead of silently mis-configuring dymos.

Everything that imports aviary is inside functions -- the module stays
importable in the main workspace venv (see the dependency note in
pyproject.toml).
"""

from __future__ import annotations

import copy
import difflib
from typing import Any

MISSION_METHODS = ("energy_state",)

# phase_info values that upstream expresses as (value, units) tuples. When an
# override provides a bare number for one of these, it is wrapped with the
# default's units; a [value, units] pair overrides both.
_TOP_LEVEL_PHASES = ("pre_mission", "post_mission")


def _suggest(key: str, valid) -> str:
    close = difflib.get_close_matches(key, list(valid), n=1)
    return f" Did you mean {close[0]!r}?" if close else ""


def default_phase_info(mission_method: str = "energy_state") -> dict:
    """Return a deep copy of the upstream default phase_info for the method."""
    if mission_method not in MISSION_METHODS:
        raise ValueError(
            f"Unsupported mission_method {mission_method!r}. Supported: "
            f"{', '.join(MISSION_METHODS)}. (2DOF/GASP missions are not wired "
            f"up in this server yet.)"
        )
    import importlib

    mod = importlib.import_module("aviary.models.missions.energy_state_default")
    return copy.deepcopy(mod.phase_info)


def _merge_options(target: dict, overrides: dict, context: str) -> None:
    """Merge override keys into target, validating names and wrapping units."""
    for key, val in overrides.items():
        if key not in target:
            raise ValueError(
                f"Unknown option {key!r} in {context}. Valid: "
                f"{sorted(target)}.{_suggest(key, target)}"
            )
        default = target[key]
        if isinstance(default, tuple) and len(default) == 2 and not isinstance(val, tuple):
            # (value, units) slot: allow bare value (keep units) or [value, units]
            if isinstance(val, (list,)) and len(val) == 2 and isinstance(val[1], str):
                target[key] = (val[0], val[1])
            else:
                target[key] = (val, default[1])
        else:
            target[key] = val


def build_phase_info(
    mission_method: str = "energy_state",
    target_range_nm: float | None = None,
    include_takeoff: bool | None = None,
    include_landing: bool | None = None,
    phase_options: dict[str, dict[str, Any]] | None = None,
) -> dict:
    """Build a validated phase_info dict from the method default + overrides.

    ``phase_options`` maps phase name -> user_options overrides, e.g.
    ``{"cruise": {"num_segments": 3, "mach_final": 0.75}}``. Option names are
    validated against the default phase's user_options; (value, units) tuple
    slots accept a bare number (default units kept) or a [value, units] pair.
    """
    phase_info = default_phase_info(mission_method)

    if include_takeoff is not None:
        phase_info["pre_mission"]["include_takeoff"] = bool(include_takeoff)
    if include_landing is not None:
        phase_info["post_mission"]["include_landing"] = bool(include_landing)
    if target_range_nm is not None:
        if target_range_nm <= 0:
            raise ValueError(f"target_range_nm must be positive (got {target_range_nm})")
        phase_info["post_mission"]["constrain_range"] = True
        phase_info["post_mission"]["target_range"] = (float(target_range_nm), "nmi")

    for phase_name, options in (phase_options or {}).items():
        if phase_name in _TOP_LEVEL_PHASES:
            _merge_options(phase_info[phase_name], options, f"{phase_name!r}")
            continue
        if phase_name not in phase_info:
            valid = [k for k in phase_info if k not in _TOP_LEVEL_PHASES]
            raise ValueError(
                f"Unknown phase {phase_name!r}. Valid phases: {sorted(valid)}."
                f"{_suggest(phase_name, valid)}"
            )
        if not isinstance(options, dict):
            raise ValueError(f"phase_options[{phase_name!r}] must be a dict of user_options")
        _merge_options(
            phase_info[phase_name]["user_options"],
            options,
            f"phase {phase_name!r} user_options",
        )

    return phase_info


def summarize_phase_info(phase_info: dict) -> dict:
    """Small JSON-safe summary of a phase_info for envelopes and session state."""
    summary: dict[str, Any] = {}
    for name, cfg in phase_info.items():
        if name in _TOP_LEVEL_PHASES:
            summary[name] = {
                k: (list(v) if isinstance(v, tuple) else v)
                for k, v in cfg.items()
                if isinstance(v, (bool, int, float, str, tuple))
            }
            continue
        user = cfg.get("user_options", {})

        def _val(key):
            v = user.get(key)
            return list(v) if isinstance(v, tuple) else v

        summary[name] = {
            "num_segments": user.get("num_segments"),
            "order": user.get("order"),
            "mach_initial": _val("mach_initial"),
            "mach_final": _val("mach_final"),
            "altitude_initial": _val("altitude_initial"),
            "altitude_final": _val("altitude_final"),
        }
    return summary
