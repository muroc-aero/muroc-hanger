"""Aircraft definition tools -- templates, deck overrides, mission config."""

from __future__ import annotations

from typing import Annotated, Any

from hangar.avy.state import sessions as _sessions
from hangar.avy.config.defaults import DEFAULT_MISSION_METHOD
from hangar.avy.templates import AIRCRAFT_TEMPLATES, get_template
from hangar.avy.missions import (
    MISSION_METHODS,
    build_phase_info,
    summarize_phase_info,
)
from hangar.avy.validators import validate_aircraft_exists, validate_deck_overrides


async def list_aircraft_templates() -> dict:
    """List the available aircraft template decks.

    Templates are Aviary's shipped model decks (``aircraft:*``/``mission:*``
    CSV input files) plus the upstream benchmark decks. Each entry reports the
    legacy mass method (FLOPS/GASP) and the mission method
    (``energy_state``/``2DOF``) the deck is calibrated for.
    """
    return {
        "count": len(AIRCRAFT_TEMPLATES),
        "templates": {
            name: {k: v for k, v in cfg.items() if k != "deck"}
            for name, cfg in AIRCRAFT_TEMPLATES.items()
        },
    }


async def load_aircraft_template(
    template: Annotated[
        str,
        "Template name. Valid: " + ", ".join(sorted(AIRCRAFT_TEMPLATES)) + ". "
        "Call list_aircraft_templates for descriptions.",
    ],
    name: Annotated[str, "Name for this aircraft (used in subsequent calls)"] = "aircraft",
    session_id: Annotated[str, "Session ID for state management"] = "default",
) -> dict:
    """Seed an aircraft from a shipped Aviary model deck.

    The deck is a complete ``name,value,units`` input file; individual
    variables can then be overridden with ``define_aircraft``, and the
    mission configured with ``configure_mission``. The default energy_state
    mission is used if configure_mission is never called.
    """
    cfg = get_template(template)

    session = _sessions.get(session_id)
    session.aircraft[name] = {
        "template": template,
        "deck": cfg["deck"],
        "mass_method": cfg["mass_method"],
        "mission_method": cfg["mission_method"],
        "overrides": {},
        "mission": None,
    }

    runnable = cfg["mission_method"] in MISSION_METHODS
    return {
        "aircraft_name": name,
        "template": template,
        "deck": cfg["deck"],
        "mass_method": cfg["mass_method"],
        "mission_method": cfg["mission_method"],
        "status": f"Aircraft '{name}' loaded from template '{template}'. "
        + (
            "Call run_sizing (optionally after define_aircraft / configure_mission)."
            if runnable
            else "NOTE: this deck is calibrated for a 2DOF mission, which this "
            "server does not run yet -- analysis calls will be rejected."
        ),
    }


async def define_aircraft(
    aircraft_name: Annotated[str, "Name of aircraft loaded by load_aircraft_template"] = "aircraft",
    overrides: Annotated[
        dict[str, Any] | None,
        "Aviary deck variable overrides as {name: value} or {name: [value, units]}. "
        "Names use the 'aircraft:wing:span' hierarchy and are validated against "
        "Aviary's variable metadata (unknown names error with close matches). "
        "Example: {'aircraft:wing:aspect_ratio': 11.5, "
        "'mission:design:gross_mass': [175000, 'lbm']}",
    ] = None,
    session_id: Annotated[str, "Session ID"] = "default",
) -> dict:
    """Override individual aircraft/mission deck variables on a loaded aircraft.

    Overrides accumulate across calls (later values win). They are applied to
    the deck's AviaryValues at run time, using metadata default units when a
    bare value is given.
    """
    session = _sessions.get(session_id)
    aircraft_cfg = validate_aircraft_exists(session, aircraft_name)

    overrides = overrides or {}
    validate_deck_overrides(overrides)
    aircraft_cfg["overrides"].update(overrides)

    return {
        "aircraft_name": aircraft_name,
        "overrides": aircraft_cfg["overrides"],
        "status": f"{len(overrides)} override(s) applied "
        f"({len(aircraft_cfg['overrides'])} total on '{aircraft_name}').",
    }


async def configure_mission(
    aircraft_name: Annotated[str, "Name of aircraft loaded by load_aircraft_template"] = "aircraft",
    mission_method: Annotated[
        str,
        "Equations-of-motion family. Currently only 'energy_state' "
        "(FLOPS-style height-energy) is supported.",
    ] = DEFAULT_MISSION_METHOD,
    target_range_nm: Annotated[
        float | None,
        "Design mission range (nmi). Sets post_mission constrain_range + target_range.",
    ] = None,
    include_takeoff: Annotated[
        bool | None, "Include the detailed takeoff phase in pre_mission"
    ] = None,
    include_landing: Annotated[
        bool | None, "Include the detailed landing phase in post_mission"
    ] = None,
    phase_options: Annotated[
        dict[str, dict] | None,
        "Per-phase user_options overrides, e.g. {'cruise': {'num_segments': 3, "
        "'mach_final': 0.75}, 'climb': {'altitude_final': [35000, 'ft']}}. "
        "Phase and option names are validated against the mission-method "
        "defaults; (value, units) options accept a bare number (default units "
        "kept) or a [value, units] pair.",
    ] = None,
    session_id: Annotated[str, "Session ID"] = "default",
) -> dict:
    """Configure the mission (phase_info) for an aircraft.

    Builds the phase_info from the mission-method default (climb/cruise/descent
    for energy_state) plus the given overrides, and stores it on the aircraft.
    Calling again rebuilds from the defaults (overrides do not accumulate).
    """
    session = _sessions.get(session_id)
    aircraft_cfg = validate_aircraft_exists(session, aircraft_name)

    if aircraft_cfg["mission_method"] not in MISSION_METHODS:
        raise ValueError(
            f"Aircraft '{aircraft_name}' uses a "
            f"{aircraft_cfg['mission_method']!r} deck, which this server "
            f"cannot run yet. Load an energy_state template instead."
        )

    phase_info = build_phase_info(
        mission_method=mission_method,
        target_range_nm=target_range_nm,
        include_takeoff=include_takeoff,
        include_landing=include_landing,
        phase_options=phase_options,
    )

    aircraft_cfg["mission"] = {
        "mission_method": mission_method,
        "target_range_nm": target_range_nm,
        "phase_info": phase_info,
    }

    return {
        "aircraft_name": aircraft_name,
        "mission_method": mission_method,
        "target_range_nm": target_range_nm,
        "phases": summarize_phase_info(phase_info),
        "status": f"Mission configured for '{aircraft_name}'. Call run_sizing.",
    }
