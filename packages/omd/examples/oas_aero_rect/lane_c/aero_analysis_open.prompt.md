# Task: Rectangular Wing at Transonic Cruise

Find the lift and drag coefficients of a plain rectangular wing at a
transonic cruise point using a vortex-lattice aerodynamic analysis.

## The wing and the flight condition

- Rectangular planform: 10 m span, 1 m chord, no sweep, taper, or dihedral.
- Discretise it coarsely: 2 chordwise mesh points and 7 spanwise mesh points,
  exploiting the spanwise symmetry (model half the wing).
- Flight condition: 248.136 m/s at Mach 0.84, 5 degrees angle of attack,
  air density 0.38 kg/m^3, Reynolds number 1e6 per metre.
- Include viscous drag on top of the induced drag, with a parasite drag
  coefficient of 0.015.

## What matters

- The mesh resolution above is part of the specification -- CL and CD depend
  on it, so do not refine or coarsen it.
- Sanity-check the result: is CL plausible for a rectangular wing at 5
  degrees, and is CD dominated by the right contributions? Record that
  interpretation.

## Report

CL and CD at the analysis point.

This task deliberately does not name the component type, parameter keys, or
tool workflow. Consult the server's own reference material to choose them.
