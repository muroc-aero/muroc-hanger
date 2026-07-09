# Lane C -- agent prompts for the OAS wing-mass case

Two prompt flavours for the blind-agent stage of Lane C (see
`docs/parity-lanes-and-agent-eval.md` §5):

- `coupled_sizing.prompt.md` -- **closed**: names the tools, template,
  subsystem, and call order. Certifies the tool surface computes the right
  numbers when driven correctly.
- `coupled_sizing_open.prompt.md` -- **open**: states only the engineering
  goal (physics-based wing mass replacing the empirical estimate); the
  agent must discover `add_external_subsystem`, the `oas_wing_mass`
  registry entry, and the baseline-contrast idea from the server's own
  affordances.

Scoring: reported metrics compare against Lane A
(`lane_a/coupled_sizing.py`) with the tolerances in `../shared.py`; the
open prompt's empirical-vs-physics contrast is scored against the
`test_oas_wing_mass_differs_from_flops` expectation
(`MIN_WING_MASS_CONTRAST_REL`).
