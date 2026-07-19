# Task: Aerostructural Analysis of a Rectangular Wing

Find the lift and drag coefficients of a rectangular wing when its structure
is allowed to deform: a coupled aerodynamic + structural analysis where a
vortex lattice loads a tubular-spar finite-element model and the deformed
shape feeds back into the aerodynamics.

## The wing, structure, and flight condition

- Rectangular planform: 10 m span, 1 m chord, 7 spanwise and 2 chordwise
  mesh points, symmetric half-model.
- Structure: a tube spar in an aluminium-class material -- Young's modulus
  70 GPa, shear modulus 30 GPa, yield stress 500 MPa, material density
  3000 kg/m^3.
- Tube wall thickness controlled at three stations, root to tip:
  10 mm, 20 mm, 10 mm.
- Flight condition: 248.136 m/s at Mach 0.84, 5 degrees angle of attack,
  air density 0.38 kg/m^3, Reynolds number 1e6 per metre, viscous drag
  included.

## What matters

- The aero-structure coupling is a genuine two-way loop; make sure it is
  driven to convergence with a proper nonlinear solve, not a single pass.
- Check the structure is safe (stress below yield with margin) and record
  that interpretation alongside the aerodynamic result.

## Report

CL and CD of the converged aerostructural solution.

This task deliberately does not name the component type, parameter keys, or
tool workflow. Consult the server's own reference material to choose them.
