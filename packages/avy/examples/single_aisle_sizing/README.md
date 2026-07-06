# single_aisle_sizing -- Aviary parity example

The same engineering problem -- size the advanced single-aisle transport
(FLOPS mass + aero) on the default 3-phase energy_state mission with a
1906 nmi range constraint, under SLSQP -- solved through each lane
(see `docs/parity-lanes-and-agent-eval.md`):

- **Lane A** (`lane_a/sizing.py`): raw Aviary Level 1 (`run_aviary`), no
  hangar code. The reference, pinned to `GOLDEN` anchors from Aviary v1.0.1.
- **Lane B** (`lane_b/sizing.json`): the identical problem as an MCP
  tool-call script (`load_aircraft_template -> configure_mission ->
  run_sizing`), replayed in process through `hangar.sdk.cli.runner.run_tool`.

Parameters and tolerances live in `shared.py` (the contract). Headline
metrics: `gross_mass_lbm`, `total_fuel_mass_lbm`, `range_nmi`,
`final_time_min`.

An omd Lane C (plan authored through `mcp__omd__*` tools by a blind agent)
is future work -- it needs an omd `avy` factory, which cannot live in the
main venv until the numpy-2 split is resolved (see
`docs/aviary-server-plan.md`).

Run (inside the isolated Aviary venv; see `scripts/setup-avy-venv.sh`):

```bash
.venv-avy/bin/python -m pytest packages/avy/examples/single_aisle_sizing/tests/ -v --rootdir=.
```

Each lane takes ~20 s; the full suite is ~1.5 min.
