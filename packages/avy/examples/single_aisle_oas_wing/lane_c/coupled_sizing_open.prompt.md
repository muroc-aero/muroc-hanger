# Task: Physics-Based Wing Mass Study (open prompt)

You have an Aviary MCP server (aircraft sizing + mission optimization,
`mcp__Aviary__*` tools).

Size a modern single-aisle transport aircraft on a ~1800 nmi fixed-profile
mission, but replace the empirical (FLOPS) wing weight estimate with a
physics-based structural wing mass computed by an aerostructural analysis,
and report how far the physics-based wing mass moves from the empirical
one.

Discover the available aircraft templates, external subsystems, and
mission templates from the server's own tool descriptions and listings.
Check the run's validation findings before trusting any number, and record
your decisions in the provenance log as you go.

Report: sized gross mass (lbm), total fuel (lbm), the physics-based wing
mass (lbm), the empirical wing mass it replaced (lbm), and whether the
optimizer converged.

(The empirical value requires a second, subsystem-free sizing on the same
mission -- notice that yourself.)
