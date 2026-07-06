"""Aviary run lifecycle management.

Every Aviary run is a driver run (dymos collocation + optimizer), and the
upstream problem has two process-global hazards for a long-lived server:

- OpenMDAO problem names collide across repeated runs in one process, so
  ``_clear_problem_names()`` must be called before each run;
- reports and recorder files land in the *current working directory*
  (``reports/<problem_name>/``), so each run executes inside a managed
  per-run scratch directory under the artifact area.

``os.chdir`` is process-global, so runs are serialized behind a lock. All
aviary imports are lazy (see the dependency note in pyproject.toml).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

_RUN_LOCK = threading.Lock()

VALID_OPTIMIZERS = ("SLSQP", "IPOPT", "SNOPT")


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
    from openmdao.core.problem import _clear_problem_names
    from aviary.interface.run_aviary import run_aviary

    scratch = Path(scratch_dir) if scratch_dir else Path.cwd()
    scratch.mkdir(parents=True, exist_ok=True)

    with _RUN_LOCK:
        old_cwd = os.getcwd()
        os.chdir(scratch)
        try:
            _clear_problem_names()
            prob = run_aviary(
                aircraft_data,
                phase_info,
                optimizer=optimizer,
                max_iter=max_iter,
                make_plots=False,
                verbosity=0,
            )
        finally:
            os.chdir(old_cwd)
    return prob


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
