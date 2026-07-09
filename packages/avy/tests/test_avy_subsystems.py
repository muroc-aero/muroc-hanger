"""Unit tests for the external subsystem registry + OAS wing-mass builder.

Config validation, resampling, and the driver-knob seam are aviary-free
and run in any venv; builder construction tests importorskip aviary and
run for real via .venv-avy.
"""

from __future__ import annotations

import numpy as np
import pytest

from hangar.avy.subsystems import (
    EXTERNAL_SUBSYSTEMS,
    build_external_subsystems,
    list_external_subsystems_info,
    validate_subsystem_spec,
)
from hangar.avy.subsystems.oas_wing_mass import (
    _nested_driver_knobs,
    _resample,
    resolve_config,
)


class TestResolveConfig:
    def test_defaults_complete(self):
        resolved = resolve_config(None)
        assert resolved["cruise_mach"] == 0.785
        assert resolved["fuel_lbm"] == 40044.0
        assert len(resolved["box_upper_x"]) == 51
        assert len(resolved["twist_cp"]) == 4
        assert resolved["sub_opt_tol"] is None

    def test_unknown_key_suggests(self):
        with pytest.raises(ValueError, match="cruise_mach"):
            resolve_config({"cruise_mac": 0.8})

    def test_wrong_array_length_rejected(self):
        with pytest.raises(ValueError, match="length 4"):
            resolve_config({"twist_cp": [0.0, 1.0]})

    def test_coarse_counts_resample_defaults(self):
        resolved = resolve_config({"num_box_cp": 15, "num_twist_cp": 3})
        assert len(resolved["box_upper_y"]) == 15
        assert len(resolved["skin_thickness_cp"]) == 3
        # endpoints preserved by linear resampling
        assert resolved["box_upper_x"][0] == pytest.approx(0.1)
        assert resolved["box_upper_x"][-1] == pytest.approx(0.6)

    def test_explicit_array_must_match_counts(self):
        with pytest.raises(ValueError, match="length 15"):
            resolve_config({"num_box_cp": 15, "box_upper_x": list(np.linspace(0.1, 0.6, 51))})

    def test_fuel_none_means_deck_driven(self):
        assert resolve_config({"fuel_lbm": None})["fuel_lbm"] is None

    def test_scalar_type_checked(self):
        with pytest.raises(ValueError, match="must be a number"):
            resolve_config({"cruise_mach": "fast"})

    def test_knob_validation(self):
        with pytest.raises(ValueError, match="sub_opt_max_iter"):
            resolve_config({"sub_opt_max_iter": 0})
        assert resolve_config({"sub_opt_tol": 1e-6})["sub_opt_tol"] == 1e-6


def test_resample_identity_and_endpoints():
    vals = [1.0, 2.0, 4.0, 8.0]
    assert _resample(vals, 4) == vals
    down = _resample(vals, 3)
    assert down[0] == 1.0 and down[-1] == 8.0 and len(down) == 3


class TestRegistry:
    def test_listing_is_json_safe(self):
        info = list_external_subsystems_info()
        assert "oas_wing_mass" in info
        entry = info["oas_wing_mass"]
        assert "advanced_single_aisle" in entry["supported_decks"]
        assert "cruise_mach" in entry["config_keys"]
        assert not any(callable(v) for v in entry.values())

    def test_unknown_name_suggests(self):
        with pytest.raises(ValueError, match="oas_wing_mass"):
            validate_subsystem_spec("oas_wing_mas")

    def test_validate_returns_resolved(self):
        resolved = validate_subsystem_spec("oas_wing_mass", {"cruise_mach": 0.78})
        assert resolved["cruise_mach"] == 0.78


def test_nested_driver_knobs_reach_the_driver():
    om = pytest.importorskip("openmdao.api")

    prob = om.Problem()
    prob.model.add_subsystem(
        "comp", om.ExecComp("y = (x - 3.0)**2"), promotes=["*"]
    )
    prob.model.add_design_var("x", lower=-10, upper=10)
    prob.model.add_objective("y")
    prob.driver = om.ScipyOptimizeDriver(optimizer="SLSQP")
    prob.driver.options["tol"] = 1e-9
    prob.setup()

    with _nested_driver_knobs(tol=1e-3, max_iter=7):
        prob.run_driver()
    assert prob.driver.options["tol"] == 1e-3
    assert prob.driver.options["maxiter"] == 7

    # seam restored: a later run must not be re-patched
    prob.driver.options["tol"] = 1e-9
    prob.run_driver()
    assert prob.driver.options["tol"] == 1e-9


class TestBuilderInAviaryVenv:
    @pytest.fixture(autouse=True)
    def _needs_stack(self):
        pytest.importorskip("aviary")
        pytest.importorskip("openaerostruct")
        pytest.importorskip("ambiance")

    def _setup_group(self, config=None):
        import openmdao.api as om

        (builder,) = build_external_subsystems(
            [{"name": "oas_wing_mass", "config": config or {}}]
        )
        import aviary.api as av

        prob = om.Problem()
        prob.model.add_subsystem(
            "wing_mass", builder.build_pre_mission(av.AviaryValues()), promotes=["*"]
        )
        prob.setup()
        return prob

    def test_config_values_reach_component_inputs(self):
        prob = self._setup_group({"cruise_mach": 0.78, "engine_mass_lbm": 8000.0})
        prob.final_setup()  # resolve connections without running a sub-opt
        assert prob.get_val("wing_mass.aerostructures.cruise_Mach").item() == 0.78
        # unit conversion applied on the connection (config lbm -> component kg)
        got = prob.get_val("wing_mass.aerostructures.engine_mass", units="lbm").item()
        assert got == pytest.approx(8000.0)

    def test_wing_mass_promoted_onto_aviary_variable(self):
        import aviary.api as av

        prob = self._setup_group()
        promoted = {
            meta["prom_name"]
            for _, meta in prob.model.list_outputs(prom_name=True, out_stream=None)
        }
        assert av.Aircraft.Wing.MASS in promoted

    def test_deck_driven_fuel_promotes_capacity(self):
        import aviary.api as av

        prob = self._setup_group({"fuel_lbm": None})
        promoted_inputs = {
            meta["prom_name"]
            for _, meta in prob.model.list_inputs(prom_name=True, out_stream=None)
        }
        assert av.Aircraft.Fuel.WING_FUEL_MASS_CAPACITY in promoted_inputs

    def test_coarse_smoke_config_builds(self):
        prob = self._setup_group({"num_box_cp": 15, "num_twist_cp": 3})
        val = prob.get_val("wing_mass.aerostructures.box_upper_x")
        assert val.shape == (15,)
