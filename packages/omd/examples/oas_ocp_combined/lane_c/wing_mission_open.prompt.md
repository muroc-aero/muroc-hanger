# Task: Wing Aero and Caravan Mission, Side by Side

Run two independent analyses inside one plan: a vortex-lattice analysis of a
Caravan-like wing at its cruise point, and a stock Cessna 208 Caravan
three-phase mission. The two must stay uncoupled -- the wing result must not
feed the mission; this is a composition exercise, not a coupled study.

## The wing analysis

- Rectangular planform, 15.87 m span, 1.64 m chord.
- 2 chordwise and 7 spanwise mesh points, symmetric half-model.
- Include viscous drag with a parasite drag coefficient of 0.015.
- Flight condition: 66.4 m/s at Mach 0.194, 3 degrees angle of attack,
  sea-level density 1.225 kg/m^3, Reynolds number 1e6 per metre.

## The mission

- Stock Caravan, standard single turboprop.
- 250 NM range, cruising at 18,000 ft.
- Climb at 850 ft/min holding 104 knots equivalent airspeed; cruise at
  129 knots equivalent airspeed; descend at 400 ft/min holding 100 knots
  equivalent airspeed; 11 integration points per phase.

## What matters

- Both analyses live in the same plan and the same run, with nothing shared
  or connected between them -- make the no-coupling choice explicit rather
  than relying on defaults.
- Confirm the run converged and interpret both results.

## Report

The wing's CL and CD, and the mission's fuel burn, operating empty weight,
and maximum takeoff weight in kg.

This task deliberately does not name the component types, parameter keys, or
tool workflow. Consult the server's own reference material to choose them.
