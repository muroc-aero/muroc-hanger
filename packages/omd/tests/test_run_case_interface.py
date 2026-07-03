"""run_plan case interface: overrides, case/study stamping, idempotency on
(study_id, case_id, attempt), and warm starts from a prior run.

This is the seam the have-agent control plane drives: one base plan, many
cases, each invoked as run_plan(plan, overrides=..., case_id=..., ...).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hangar.omd.assemble import assemble_plan
from hangar.omd.db import plan_store_dir, query_entity, query_run_key
from hangar.omd.run import run_plan
from hangar.results_reader.db import _get_conn

FIXTURES = Path(__file__).parent / "fixtures"


def _paraboloid_f(x: float, y: float) -> float:
    return (x - 3.0) ** 2 + x * y + (y + 4.0) ** 2 - 3.0


@pytest.fixture()
def analysis_plan(tmp_path):
    out = tmp_path / "plan.yaml"
    result = assemble_plan(FIXTURES / "paraboloid_analysis", output=out)
    assert result["errors"] == []
    return out


@pytest.fixture()
def opt_plan(tmp_path):
    out = tmp_path / "opt_plan.yaml"
    result = assemble_plan(FIXTURES / "paraboloid_optimization", output=out)
    assert result["errors"] == []
    return out


def _run(plan, **kwargs):
    kwargs.setdefault("mode", "analysis")
    kwargs.setdefault("recording_level", "minimal")
    return run_plan(plan, **kwargs)


class TestOverrides:
    def test_overrides_applied(self, analysis_plan):
        result = _run(analysis_plan,
                      overrides={"operating_points.x": 5.0,
                                 "operating_points.y": 2.0})
        assert result["status"] == "completed"
        assert result["summary"]["f_xy"] == pytest.approx(_paraboloid_f(5.0, 2.0))

    def test_base_plan_file_untouched(self, analysis_plan):
        before = analysis_plan.read_text()
        _run(analysis_plan, overrides={"operating_points.x": 5.0})
        assert analysis_plan.read_text() == before

    def test_bad_override_path_fails_cleanly(self, analysis_plan):
        result = _run(analysis_plan,
                      overrides={"components[nonexistent].config.x": 1.0})
        assert result["status"] == "failed"
        assert result["run_id"] is None
        assert result["errors"][0]["path"] == "overrides"

    def test_override_breaking_schema_fails_validation(self, analysis_plan):
        result = _run(analysis_plan, overrides={"components": "not-a-list"})
        assert result["status"] == "failed"
        assert result["run_id"] is None
        assert result["errors"]


class TestCaseStamping:
    def test_effective_plan_stored_and_stamped(self, analysis_plan):
        result = _run(analysis_plan,
                      overrides={"operating_points.x": 1.0},
                      case_id="x1_y2", study_id="brelje-01", attempt=1)
        assert result["status"] == "completed"
        store_path = plan_store_dir() / "brelje-01--x1_y2" / "v1.yaml"
        assert store_path.exists()
        stored = yaml.safe_load(store_path.read_text())
        assert stored["metadata"]["id"] == "brelje-01--x1_y2"
        assert stored["metadata"]["study"] == "brelje-01"
        assert stored["metadata"]["case_id"] == "x1_y2"
        assert stored["metadata"]["version"] == 1
        assert stored["operating_points"]["x"] == 1.0

    def test_run_record_carries_case_identity(self, analysis_plan):
        import json

        result = _run(analysis_plan, case_id="c1", study_id="s1", attempt=2)
        run = query_entity(result["run_id"])
        meta = json.loads(run["metadata"])
        assert meta["study_id"] == "s1"
        assert meta["case_id"] == "c1"
        assert meta["attempt"] == 2

    def test_run_grouped_under_study_entity(self, analysis_plan):
        result = _run(analysis_plan, case_id="c1", study_id="s1", attempt=1)
        assert query_entity("study-s1/v1") is not None
        conn = _get_conn()
        edge = conn.execute(
            "SELECT 1 FROM prov_edges WHERE relation = 'partOf'"
            " AND subject_id = ? AND object_id = 'study-s1/v1'",
            (result["run_id"],),
        ).fetchone()
        assert edge is not None


class TestIdempotency:
    def test_same_key_replays_without_rerun(self, analysis_plan):
        first = _run(analysis_plan, case_id="c1", study_id="s1", attempt=1)
        assert first["status"] == "completed"
        assert "idempotent" not in first
        second = _run(analysis_plan, case_id="c1", study_id="s1", attempt=1)
        assert second["idempotent"] is True
        assert second["run_id"] == first["run_id"]
        assert second["summary"]["f_xy"] == first["summary"]["f_xy"]
        # only one run entity exists for the key
        conn = _get_conn()
        n = conn.execute(
            "SELECT COUNT(*) FROM entities WHERE entity_type = 'run_record'"
        ).fetchone()[0]
        assert n == 1

    def test_new_attempt_runs_again(self, analysis_plan):
        first = _run(analysis_plan, case_id="c1", study_id="s1", attempt=1)
        second = _run(analysis_plan, case_id="c1", study_id="s1", attempt=2)
        assert "idempotent" not in second
        assert second["run_id"] != first["run_id"]

    def test_failed_run_is_replayed_too(self, analysis_plan):
        # A schema-valid but unmaterializable component type fails at
        # materialize time, after a run_id exists -- the key must stick so
        # the same attempt is not silently re-executed.
        bad = {"components[paraboloid].type": "nope/Missing"}
        first = _run(analysis_plan, overrides=bad,
                     case_id="c1", study_id="s1", attempt=1)
        assert first["status"] == "failed"
        assert first["run_id"] is not None
        second = _run(analysis_plan, overrides=bad,
                      case_id="c1", study_id="s1", attempt=1)
        assert second["idempotent"] is True
        assert second["status"] == "failed"
        assert second["run_id"] == first["run_id"]

    def test_key_requires_full_triple(self, analysis_plan):
        # case_id without study_id/attempt: stamped, but never idempotent
        first = _run(analysis_plan, case_id="c1")
        second = _run(analysis_plan, case_id="c1")
        assert "idempotent" not in second
        assert second["run_id"] != first["run_id"]
        assert query_run_key("", "c1", 0) is None


class TestWarmStart:
    def test_warm_start_seeds_dv_initials(self, opt_plan):
        donor = _run(opt_plan, mode="optimize", recording_level="driver")
        assert donor["status"] == "converged"
        result = _run(opt_plan, mode="optimize", recording_level="driver",
                      warm_start_run=donor["run_id"],
                      case_id="ws", study_id="s1", attempt=1)
        assert result["status"] == "converged"
        stored = yaml.safe_load(
            (plan_store_dir() / "s1--ws" / "v1.yaml").read_text())
        initials = {dv["name"]: dv.get("initial")
                    for dv in stored["design_variables"]}
        # seeded at the donor's optimum: x=20/3, y=-22/3
        assert initials["x"] == pytest.approx(20.0 / 3.0, rel=1e-4)
        assert initials["y"] == pytest.approx(-22.0 / 3.0, rel=1e-4)

    def test_warm_start_records_used_edge(self, opt_plan):
        donor = _run(opt_plan, mode="optimize", recording_level="driver")
        result = _run(opt_plan, mode="optimize", recording_level="driver",
                      warm_start_run=donor["run_id"])
        conn = _get_conn()
        edge = conn.execute(
            "SELECT 1 FROM prov_edges WHERE relation = 'used'"
            " AND subject_id = ? AND object_id = ?",
            (f"act-execute-{result['run_id']}", donor["run_id"]),
        ).fetchone()
        assert edge is not None

    def test_missing_donor_degrades_to_cold_start(self, opt_plan):
        result = _run(opt_plan, mode="optimize", recording_level="driver",
                      warm_start_run="run-does-not-exist")
        assert result["status"] == "converged"
        assert result["errors"] == []
