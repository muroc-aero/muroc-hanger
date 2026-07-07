"""Unit tests for the avy/Sizing subprocess factory (no aviary needed).

The factory registers and builds in the main venv with zero aviary
dependency; only compute() reaches for the isolated .venv-avy. These tests
cover the registry, build/setup, config validation, and the
missing-interpreter error path -- the real subprocess runs live in the
parity suites (packages/omd/examples/tests/, skip-gated on .venv-avy).
"""

from __future__ import annotations

import pytest

from hangar.omd.registry import get_factory, list_factories

DECK = "models/aircraft/advanced_single_aisle/advanced_single_aisle_FLOPS.csv"


def test_factory_registered():
    assert "avy/Sizing" in list_factories()


def test_build_requires_deck():
    build = get_factory("avy/Sizing")
    with pytest.raises(ValueError, match="deck"):
        build({}, {})


def test_build_produces_problem_with_outputs():
    build = get_factory("avy/Sizing")
    prob, meta = build({"deck": DECK, "target_range_nm": 1906.0}, {})
    prob.setup()

    assert meta["point_name"] == "aviary"
    assert meta["component_family"] == "avy"
    assert "gross_mass_lbm" in meta["output_names"]
    assert "converged" in meta["output_names"]
    # target_range_nm configured -> exposed as an input for sweeps/DOE
    assert meta["var_paths"]["target_range_nm"] == "target_range_nm"
    assert meta["initial_values"]["target_range_nm"] == 1906.0
    assert float(prob.get_val("target_range_nm")[0]) == 1906.0


def test_operating_point_overrides_target_range():
    build = get_factory("avy/Sizing")
    _prob, meta = build(
        {"deck": DECK, "target_range_nm": 1906.0},
        {"target_range_nm": 2500.0},
    )
    assert meta["initial_values"]["target_range_nm"] == 2500.0


def test_no_target_range_means_no_input():
    build = get_factory("avy/Sizing")
    prob, meta = build({"deck": DECK}, {})
    prob.setup()
    assert "target_range_nm" not in meta["var_paths"]


def test_missing_venv_gives_setup_instructions(tmp_path):
    build = get_factory("avy/Sizing")
    prob, _meta = build(
        {"deck": DECK, "avy_python": str(tmp_path / "nope" / "python")}, {}
    )
    prob.setup()
    with pytest.raises(Exception, match="setup-avy-venv"):
        prob.run_model()
