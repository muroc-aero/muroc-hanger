"""Aviary run lifecycle management.

Every Aviary run is a driver run (dymos collocation + optimizer), and the
upstream problem has two process-global hazards for a long-lived server:

- OpenMDAO problem names collide across repeated runs in one process, so
  ``_clear_problem_names()`` must be called before each run;
- reports, recorder files, and off-design ``*_out`` directories land in the
  *current working directory*, so each run executes inside a managed
  per-run scratch directory under the artifact area.

``os.chdir`` is process-global, so runs are serialized behind a lock. All
aviary imports are lazy (see the dependency note in pyproject.toml).

Off-design and payload-range analyses need a live sized AviaryProblem, and
no live Problem is cached in the session (same policy as hangar-pyc, whose
off-design rebuilds and re-solves the design point every call) -- so those
entry points re-run the sizing inside the same scratch/lock block and then
fly the off-design mission(s) from it.
"""

from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path

_RUN_LOCK = threading.Lock()

# os.chdir is process-global, so while a run holds the lock every relative
# path in the process resolves against that run's scratch dir. Anchor
# scratch paths to the cwd at import time (server/CLI startup, before any
# run) so a queued run's scratch never resolves inside the active run's.
_LAUNCH_CWD = Path.cwd()

VALID_OPTIMIZERS = ("SLSQP", "IPOPT", "SNOPT")

# Tool-facing mission_type -> Aviary ProblemType value
OFF_DESIGN_TYPES = {
    "max_range": "off_design_max_range",
    "min_fuel": "off_design_min_fuel",
}


def require_aviary():
    """Import and return the aviary package, with an actionable error if absent."""
    try:
        import aviary  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "The 'aviary' package is not installed in this environment. "
            "Aviary requires openmdao>=3.43 (numpy>=2) and cannot share the "
            "main hangar venv; run `bash scripts/setup-avy-venv.sh` and use "
            ".venv-avy (avy-server / avy-cli run from it), or use the "
            "hangar-avy Docker image."
        ) from exc
    return aviary


def check_optimizer_available(optimizer: str) -> None:
    """Raise if the requested optimizer cannot run in this environment."""
    if optimizer not in VALID_OPTIMIZERS:
        raise ValueError(
            f"Unknown optimizer {optimizer!r}. Valid: {', '.join(VALID_OPTIMIZERS)}"
        )
    if optimizer in ("IPOPT", "SNOPT"):
        try:
            from pyoptsparse import OPT  # noqa: F401
        except ImportError:
            raise ValueError(
                f"Optimizer {optimizer!r} requires pyoptsparse, which is not "
                "installed (it is not pip-installable; see "
                "https://github.com/OpenMDAO/build_pyoptsparse). Use "
                "optimizer='SLSQP' instead."
            ) from None


@contextlib.contextmanager
def _scratch_run(scratch_dir: str | Path | None):
    """Serialize the run and execute it inside the scratch cwd.

    The scratch path is anchored to the launch cwd, and created only after
    the lock is held -- doing either against the *current* cwd would race
    with the run that holds the lock (its chdir is process-global).
    """
    from openmdao.core.problem import _clear_problem_names

    scratch = Path(scratch_dir) if scratch_dir else _LAUNCH_CWD
    if not scratch.is_absolute():
        scratch = _LAUNCH_CWD / scratch

    with _RUN_LOCK:
        old_cwd = os.getcwd()
        scratch.mkdir(parents=True, exist_ok=True)
        os.chdir(scratch)
        try:
            _clear_problem_names()
            yield
        finally:
            os.chdir(old_cwd)


def _solve_sizing(aircraft_data, phase_info, optimizer, max_iter):
    """Run the sizing optimization; caller must hold the scratch context."""
    from aviary.interface.run_aviary import run_aviary

    return run_aviary(
        aircraft_data,
        phase_info,
        optimizer=optimizer,
        max_iter=max_iter,
        make_plots=False,
        verbosity=0,
    )


def run_sizing_problem(
    aircraft_data,
    phase_info: dict,
    optimizer: str = "SLSQP",
    max_iter: int = 50,
    scratch_dir: str | Path | None = None,
):
    """Run an Aviary sizing problem in a managed scratch cwd; return the problem.

    ``aircraft_data`` is a deck path (str) or AviaryValues. Blocking -- call
    from a worker thread (the tools use ``asyncio.to_thread``).
    """
    require_aviary()
    with _scratch_run(scratch_dir):
        return _solve_sizing(aircraft_data, phase_info, optimizer, max_iter)


def run_off_design_problem(
    aircraft_data,
    phase_info: dict,
    mission_type: str,
    optimizer: str = "SLSQP",
    max_iter: int = 50,
    scratch_dir: str | Path | None = None,
    **off_design_kwargs,
):
    """Size the aircraft, then fly an off-design mission from the sized design.

    ``mission_type`` is a key of ``OFF_DESIGN_TYPES``. ``off_design_kwargs``
    are forwarded to ``AviaryProblem.run_off_design_mission`` (e.g.
    ``mission_range``, ``mission_gross_mass``, ``cargo_mass``, ``num_pax``).
    Returns ``(sizing_prob, off_design_prob)``. Blocking.
    """
    require_aviary()
    problem_type = OFF_DESIGN_TYPES[mission_type]

    with _scratch_run(scratch_dir):
        sizing_prob = _solve_sizing(aircraft_data, phase_info, optimizer, max_iter)
        od_prob = sizing_prob.run_off_design_mission(
            problem_type=problem_type,
            optimizer=optimizer,
            verbosity=0,
            **off_design_kwargs,
        )
    return sizing_prob, od_prob


def run_payload_range_problem(
    aircraft_data,
    phase_info: dict,
    optimizer: str = "SLSQP",
    max_iter: int = 50,
    scratch_dir: str | Path | None = None,
):
    """Size the aircraft, then run the payload-range off-design missions.

    Returns ``(sizing_prob, (max_fuel_payload_prob, ferry_prob))``; the
    inner tuple is empty when the sizing did not converge (a diagram from
    an unconverged design is meaningless -- and upstream's own skip is
    verbosity-gated away at QUIET, plus it returns None rather than () when
    an off-design mission fails, so both cases are normalized here).
    Blocking; roughly 3x a plain sizing run.
    """
    require_aviary()
    with _scratch_run(scratch_dir):
        sizing_prob = _solve_sizing(aircraft_data, phase_info, optimizer, max_iter)
        if sizing_prob.result.success:
            pr_probs = sizing_prob.run_payload_range(verbosity=0) or ()
        else:
            pr_probs = ()
    return sizing_prob, pr_probs


def load_deck(deck_path: str, overrides: dict | None = None):
    """Load an aircraft deck into AviaryValues and apply variable overrides.

    ``overrides`` maps Aviary variable names (``aircraft:wing:span`` style)
    to either a bare value (metadata default units) or a [value, units] pair.
    Returns the AviaryValues when overrides exist, else the deck path itself
    (which keeps Aviary's problem naming from the file stem).
    """
    require_aviary()
    if not overrides:
        return deck_path

    from aviary.utils.process_input_decks import create_vehicle
    from aviary.variable_info.variable_meta_data import _MetaData

    aircraft_values, _guesses = create_vehicle(deck_path)
    for name, spec in overrides.items():
        if isinstance(spec, (list, tuple)) and len(spec) == 2 and isinstance(spec[1], str):
            value, units = spec
        else:
            value, units = spec, _MetaData[name]["units"]
        aircraft_values.set_val(name, value, units)
    return aircraft_values
