# Task: 737-800 Mission with Physics-Based Drag and Propulsion

Find the fuel a Boeing 737-800 burns on a 1,500 NM three-phase mission
(climb / cruise / descent) when BOTH of its empirical models are replaced by
physics-based ones: drag from a vortex-lattice wing model, and engine
performance from a dual-spool high-bypass turbofan cycle model. Wrap each as
a pre-trained surrogate rather than solving them live in the mission loop.

## The aircraft and the mission

- Start from the stock 737-800 definition that ships with the tooling
  (twin turbofan, MTOW 79,002 kg).
- 1,500 NM range, cruising at 35,000 ft.
- Climb at 2,000 ft/min holding 250 knots equivalent airspeed.
- Cruise at 256 knots equivalent airspeed.
- Descend at 1,500 ft/min holding 250 knots equivalent airspeed.
- Integrate each phase on 3 points.

## The two replacements

- Wing model: vortex lattice, 2 chordwise and 7 spanwise mesh points, twist
  described by 4 control points.
- Engine model: high-bypass turbofan cycle designed at 35,000 ft, Mach 0.8,
  5,900 lbf net thrust per engine, turbine inlet temperature 2,857 degrees
  Rankine, using tabular (not chemical-equilibrium) thermodynamics for
  tractable deck generation.

## What matters

- Both defaults must be displaced, in the same plan and the same run.
- Composing two surrogates leaves a Newton solver with an ill-conditioned
  Jacobian; expect to need a different nonlinear solution strategy for the
  mission, with generous iteration headroom.
- Expect a one-time engine-deck training step (several minutes) at the start
  of the run.
- Judge whether fuel burn and the weight statement are consistent with a
  737-800 on a 1,500 NM sector, and record that interpretation.

## Report

Fuel burn, operating empty weight, and maximum takeoff weight, all in kg.

This task deliberately does not name the component type, slot providers,
parameter keys, or tool workflow. Consult the server's own reference
material to choose them.
