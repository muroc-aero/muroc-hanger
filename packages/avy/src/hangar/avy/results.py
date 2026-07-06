"""Result extraction from a solved AviaryProblem.

Pulls the headline sizing metrics (Aviary 1.0 flat ``mission:*`` names), a
small design summary, and a downsampled per-phase mission timeseries that
the plot generators read back from the saved artifact JSON.
"""

from __future__ import annotations

import numpy as np

# Timeseries channels: artifact key -> (dymos timeseries name, units)
_TIMESERIES_CHANNELS = {
    "time_s": ("time", "s"),
    "altitude_ft": ("altitude", "ft"),
    "mach": ("mach", "unitless"),
    "mass_lbm": ("mass", "lbm"),
    "distance_nmi": ("distance", "nmi"),
    "throttle": ("throttle", "unitless"),
}

_MAX_POINTS_PER_PHASE = 60


def _get_scalar(prob, name: str, units: str) -> float | None:
    try:
        return float(np.asarray(prob.get_val(name, units=units)).ravel()[0])
    except Exception:
        return None


def extract_sizing_results(prob, phase_names: list[str]) -> dict:
    """Extract performance, design, optimizer, and timeseries data."""
    from aviary.variable_info.variables import Aircraft, Mission

    performance = {
        "gross_mass_lbm": _get_scalar(prob, Mission.GROSS_MASS, "lbm"),
        "total_fuel_mass_lbm": _get_scalar(prob, Mission.TOTAL_FUEL_MASS, "lbm"),
        "fuel_burned_lbm": _get_scalar(prob, Mission.FUEL_MASS, "lbm"),
        "operating_mass_lbm": _get_scalar(prob, Mission.OPERATING_MASS, "lbm"),
        "zero_fuel_mass_lbm": _get_scalar(prob, Mission.ZERO_FUEL_MASS, "lbm"),
        "final_mass_lbm": _get_scalar(prob, Mission.FINAL_MASS, "lbm"),
        "range_nmi": _get_scalar(prob, Mission.RANGE, "nmi"),
        "final_time_min": _get_scalar(prob, Mission.FINAL_TIME, "min"),
    }

    design = {
        "design_gross_mass_lbm": _get_scalar(prob, Aircraft.Design.GROSS_MASS, "lbm"),
        "wing_area_ft2": _get_scalar(prob, Aircraft.Wing.AREA, "ft**2"),
        "wing_span_ft": _get_scalar(prob, Aircraft.Wing.SPAN, "ft"),
    }

    success = None
    try:
        success = bool(prob.result.success)
    except Exception:
        pass
    optimizer = {"success": success}

    return {
        "performance": performance,
        "design": design,
        "optimizer": optimizer,
        "timeseries": extract_timeseries(prob, phase_names),
    }


def extract_timeseries(prob, phase_names: list[str]) -> dict:
    """Concatenated per-phase timeseries, downsampled, as JSON-safe lists."""
    series: dict[str, list] = {key: [] for key in _TIMESERIES_CHANNELS}
    phase_of_point: list[str] = []

    for phase in phase_names:
        phase_data = {}
        n_points = None
        for key, (channel, units) in _TIMESERIES_CHANNELS.items():
            try:
                vals = np.asarray(
                    prob.get_val(f"traj.{phase}.timeseries.{channel}", units=units)
                ).ravel()
            except Exception:
                continue
            phase_data[key] = vals
            n_points = len(vals)
        if not phase_data or not n_points:
            continue

        step = max(1, n_points // _MAX_POINTS_PER_PHASE)
        idx = list(range(0, n_points, step))
        if idx[-1] != n_points - 1:
            idx.append(n_points - 1)

        for key in _TIMESERIES_CHANNELS:
            vals = phase_data.get(key)
            if vals is None or len(vals) != n_points:
                series[key].extend([None] * len(idx))
            else:
                series[key].extend(float(vals[i]) for i in idx)
        phase_of_point.extend([phase] * len(idx))

    series["phase"] = phase_of_point
    return series
