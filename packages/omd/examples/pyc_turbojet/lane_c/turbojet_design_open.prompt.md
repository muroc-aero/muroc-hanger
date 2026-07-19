# Task: Size a Single-Spool Turbojet at Sea-Level Static

Run the design-point thermodynamic cycle analysis of a single-spool turbojet
at sea-level static conditions and report its headline performance.

## The engine and the design point

- Single-spool turbojet: one compressor, burner, one turbine, nozzle.
- Compressor pressure ratio 13.5 at 83% efficiency; turbine efficiency 86%.
- Shaft speed 8,070 rpm.
- Burner pressure loss 3%; nozzle velocity coefficient 0.99.
- Thermodynamics via chemical equilibrium (not table lookup).
- Design point: sea level, essentially static (Mach ~ 0), sized to hit
  11,800 lbf net thrust at a turbine inlet temperature of 2,370 degrees
  Rankine.

## What matters

- This is a design-point sizing, not an off-design excursion.
- Sanity-check the result: does net thrust hit the target, is TSFC in the
  usual 0.8-1.5 lbm/hr/lbf band for a simple turbojet, and does the overall
  pressure ratio equal the compressor's (single spool)? Record that
  interpretation.

## Report

Net thrust (Fn), thrust-specific fuel consumption (TSFC), and overall
pressure ratio (OPR) at the design point.

This task deliberately does not name the component type, parameter keys, or
tool workflow. Consult the server's own reference material to choose them.
