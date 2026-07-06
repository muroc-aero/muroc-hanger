"""Analysis tool -- run_sizing.

Every Aviary run solves the mission trajectory (dymos collocation) and the
aircraft sizing together under a driver -- there is no cheap evaluate-only
path. That is why the tool is named run_sizing and not run_mission_analysis:
the mission IS the sizing optimization.
"""

from __future__ import annotations

import asyncio
import time
from typing import Annotated

from hangar.sdk.helpers import _suppress_output
from hangar.avy.state import sessions as _sessions

from hangar.avy.config.defaults import DEFAULT_MAX_ITER, DEFAULT_OPTIMIZER
from hangar.avy.missions import MISSION_METHODS, build_phase_info, summarize_phase_info
from hangar.avy.results import extract_sizing_results
from hangar.avy.runner import (
    check_optimizer_available,
    load_deck,
    require_aviary,
    run_sizing_problem,
)
from hangar.avy.validation import validate_sizing_results
from hangar.avy.validators import validate_aircraft_exists, validate_max_iter
from hangar.avy.tools._helpers import _finalize_analysis, _make_run_id, _run_scratch_dir

_TOP_LEVEL = ("pre_mission", "post_mission")


async def run_sizing(
    aircraft_name: Annotated[str, "Name of aircraft loaded by load_aircraft_template"] = "aircraft",
    optimizer: Annotated[
        str,
        "Optimizer: 'SLSQP' (default, always available), 'IPOPT' or 'SNOPT' "
        "(require pyoptsparse; rejected with instructions when absent).",
    ] = DEFAULT_OPTIMIZER,
    max_iter: Annotated[int, "Maximum optimizer iterations"] = DEFAULT_MAX_ITER,
    run_name: Annotated[str | None, "Optional label for this run"] = None,
    session_id: Annotated[str, "Session ID"] = "default",
) -> dict:
    """Run the coupled aircraft-sizing + mission optimization (ProblemType SIZING).

    Sizes the aircraft (gross mass, fuel) while optimizing the mission
    trajectory against the configured phase_info (default: the 3-phase
    energy_state climb/cruise/descent mission). Takes tens of seconds to
    minutes depending on mission complexity.

    ALWAYS check validation.passed (the 'optimizer.success' finding) before
    trusting results: optimizer non-convergence does not raise, it returns
    the last iterate with a failed flag.

    Returns a versioned response envelope with performance (gross mass, fuel,
    range, mission time), design summary, and a downsampled mission timeseries.
    """
    t0 = time.perf_counter()
    session = _sessions.get(session_id)

    aircraft_cfg = validate_aircraft_exists(session, aircraft_name)
    if aircraft_cfg["mission_method"] not in MISSION_METHODS:
        raise ValueError(
            f"Aircraft '{aircraft_name}' uses a "
            f"{aircraft_cfg['mission_method']!r} deck, which this server "
            f"cannot run yet. Load an energy_state template instead."
        )
    check_optimizer_available(optimizer)
    validate_max_iter(max_iter)
    require_aviary()

    mission = aircraft_cfg.get("mission")
    if mission is None:
        phase_info = build_phase_info(mission_method="energy_state")
        target_range_nm = None
    else:
        phase_info = mission["phase_info"]
        target_range_nm = mission.get("target_range_nm")

    phase_names = [p for p in phase_info if p not in _TOP_LEVEL]
    run_id = _make_run_id()
    scratch_dir = _run_scratch_dir(session, session_id, run_id)

    def _run():
        aircraft_data = load_deck(aircraft_cfg["deck"], aircraft_cfg["overrides"])
        prob = run_sizing_problem(
            aircraft_data,
            phase_info,
            optimizer=optimizer,
            max_iter=max_iter,
            scratch_dir=scratch_dir,
        )
        return extract_sizing_results(prob, phase_names)

    results = await asyncio.to_thread(_suppress_output, _run)

    aircraft_cfg["sized_run_id"] = run_id

    # The default mission's target range lives in the phase_info even when
    # configure_mission was never called; recover it for the range check.
    if target_range_nm is None:
        target = phase_info.get("post_mission", {}).get("target_range")
        if target is not None and phase_info["post_mission"].get("constrain_range"):
            target_range_nm = float(target[0])

    findings = validate_sizing_results(
        results, optimizer, max_iter, target_range_nmi=target_range_nm
    )

    inputs = {
        "aircraft_name": aircraft_name,
        "template": aircraft_cfg["template"],
        "deck": aircraft_cfg["deck"],
        "overrides": aircraft_cfg["overrides"],
        "optimizer": optimizer,
        "max_iter": max_iter,
        "target_range_nm": target_range_nm,
        "phases": summarize_phase_info(phase_info),
    }

    return await _finalize_analysis(
        tool_name="run_sizing",
        run_id=run_id,
        session=session,
        session_id=session_id,
        aircraft_name=aircraft_name,
        analysis_type="sizing",
        inputs=inputs,
        results=results,
        findings=findings,
        t0=t0,
        run_name=run_name,
    )
