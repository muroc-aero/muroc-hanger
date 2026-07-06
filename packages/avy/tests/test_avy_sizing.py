"""Slow integration tests: full run_sizing through the tool surface.

Need the aviary package (run in .venv-avy; see scripts/setup-avy-venv.sh):

    .venv-avy/bin/python -m pytest packages/avy/tests/ -v
"""

from __future__ import annotations

import pytest

from hangar.avy.tools.aircraft import configure_mission
from hangar.avy.tools.analysis import run_sizing
from hangar.avy.tools.session import get_detailed_results, visualize


@pytest.mark.slow
@pytest.mark.golden_physics
async def test_run_sizing_default_mission(single_aisle):
    pytest.importorskip("aviary")

    env = await run_sizing(aircraft_name=single_aisle)

    assert env.get("error") is None
    assert env["validation"]["passed"], env["validation"]
    perf = env["results"]["performance"]

    # Golden anchors: advanced_single_aisle FLOPS deck, default energy_state
    # mission (1906 nmi), SLSQP. Values pinned from Aviary v1.0.1; a pin bump
    # that moves these is an upstream physics change, not a wrapper bug.
    assert perf["gross_mass_lbm"] == pytest.approx(116423.0, rel=2e-3)
    assert perf["total_fuel_mass_lbm"] == pytest.approx(13814.0, rel=5e-3)
    assert perf["range_nmi"] == pytest.approx(1906.0, rel=1e-6)

    # Mass hierarchy sanity
    assert perf["zero_fuel_mass_lbm"] < perf["gross_mass_lbm"]
    assert perf["operating_mass_lbm"] < perf["zero_fuel_mass_lbm"]

    # Timeseries present and phase-tagged
    ts = env["results"]["timeseries"]
    assert set(ts["phase"]) == {"climb", "cruise", "descent"}
    assert len(ts["time_s"]) == len(ts["altitude_ft"]) == len(ts["phase"])


@pytest.mark.slow
async def test_run_sizing_with_target_range_and_plots(single_aisle):
    pytest.importorskip("aviary")

    await configure_mission(aircraft_name=single_aisle, target_range_nm=1500.0)
    env = await run_sizing(aircraft_name=single_aisle, run_name="1500 nmi")

    assert env["validation"]["passed"], env["validation"]
    perf = env["results"]["performance"]
    assert perf["range_nmi"] == pytest.approx(1500.0, rel=1e-6)
    # Shorter design mission -> less fuel than the 1906 nmi default anchor
    assert perf["total_fuel_mass_lbm"] < 13814.0

    run_id = env["run_id"]
    for plot_type in ("mission_profile", "mass_breakdown", "performance_summary"):
        out = await visualize(run_id, plot_type, output="file")
        assert out[0].get("file_path"), f"{plot_type} produced no file"

    detail = await get_detailed_results(run_id, detail_level="summary")
    assert detail["results"]["gross_mass_lbm"] == pytest.approx(
        perf["gross_mass_lbm"]
    )
