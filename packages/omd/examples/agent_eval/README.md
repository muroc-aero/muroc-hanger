# Lane C Agent Eval

Stage 2 of Lane C parity coverage. Stage 1
(`../tests/test_parity_lane_c.py`) scripts the MCP tool surface in
process; this harness runs the real thing: a blind agent driving a
live omd MCP server, scored against the Lane A reference scripts.

## What it does

For each case, the harness:

1. Computes the Lane A reference by running the example's
   `lane_a/<module>.run()` in its own subprocess (one process per
   example; the `shared.py` modules collide otherwise).
2. Launches an agent via the Claude Agent SDK with:
   - the example's **open** Lane C prompt
     (`<example>/lane_c/*_open.prompt.md`) wrapped in MCP-only rules
     and a required JSON report format,
   - only the omd MCP tools allowed (stdio server, isolated data root
     in a temp dir; Bash/Read/Write/Glob/Grep/web all disallowed),
   - no access to the repo, so it cannot peek at lane_a/lane_b.
3. Parses the agent's fenced JSON report and scores each metric
   against Lane A within per-metric relative tolerances.

Exit code is nonzero if any required metric fails, so this can run in
automation (cron, CI with API credentials) as well as by hand.

## Running

Requires the Claude Code CLI (authenticated) and `claude-agent-sdk`:

```bash
# one case
uv run --with claude-agent-sdk \
    packages/omd/examples/agent_eval/eval_lane_c.py paraboloid

# all cases (every parity example except ocp_pyc_coupled)
uv run --with claude-agent-sdk \
    packages/omd/examples/agent_eval/eval_lane_c.py all

# useful flags
#   --model <name>   model override for the agent
#   --verbose        stream agent text while it works
#   --keep-data      keep the temp omd data root for inspection
```

## Cases and tolerances

Every case uses its example's open prompt: the engineering goal plus the
physical inputs (geometry, mission profile, design point), with no
factory name, slot provider, parameter key, or tool-call sequence. The
harness preamble states hard rules and the report format only -- the
agent must discover the plan-authoring workflow from the server's own
affordances (tool descriptions, the `omd://reference` resource, error
messages).

| Case | Metrics (required) | rtol |
|------|--------------------|------|
| `paraboloid` | `analysis_f_xy`, `opt_f_xy` | 1e-6, 1e-4 |
| `paraboloid` | `opt_x`, `opt_y` (warn-only: DV retrieval is a known tool-surface gap, see FEATURE_BACKLOG) | 1e-3 |
| `oas_aero_rect` | `CL`, `CD` | 1e-6 |
| `oas_aerostruct_rect` | `CL`, `CD` (headroom for the agent's solver-tolerance choice) | 1e-4 |
| `ocp_caravan_basic` | `fuel_burn_kg`, `OEW_kg`, `MTOW_kg` | 1e-3, 1e-3, 1e-6 |
| `ocp_caravan_full` | `fuel_burn_kg`, `OEW_kg`, `MTOW_kg` | 1e-3, 1e-3, 1e-6 |
| `ocp_hybrid_twin` | `fuel_burn_kg`, `OEW_kg`, `MTOW_kg` | 1e-3, 1e-3, 1e-6 |
| `oas_ocp_combined` | `wing_CL`, `wing_CD`, `fuel_burn_kg`, `OEW_kg`, `MTOW_kg` | 1e-6, 1e-6, 1e-3, 1e-3, 1e-6 |
| `ocp_oas_coupled` | `fuel_burn_kg`, `OEW_kg`, `MTOW_kg` | 1e-3, 1e-3, 1e-6 |
| `ocp_oas_direct` | `fuel_burn_kg`, `OEW_kg`, `MTOW_kg` | 1e-3, 1e-3, 1e-6 |
| `pyc_turbojet` | `Fn`, `TSFC`, `OPR` | 1e-4 |
| `ocp_three_tool` | `fuel_burn_kg`, `OEW_kg`, `MTOW_kg` | 1e-3, 1e-3, 1e-6 |
| `evt_open_sizing` | `sized_mtow_kg`, `total_mission_energy_kw_hr`, `peak_power_kw` | 1e-3 |

`ocp_pyc_coupled` has an open prompt but is not scored: its tool-surface
path shares the Lane B materializer, whose weight-slot precedence forces
an OEW passthrough (~8% OEW / ~4% fuel gap vs Lane A -- see that
example's TODO.md), so no agent can match the Lane A reference through
the tools.

`evt_open_sizing` also tests the portable (filesystem-free) path: the
agent has no config file, so it must use the in-package
`archer_midnight` template. Lane A loads that same vehicle from its
JSON, and the template is vendored from that file, so a template-built
result matches the file-based reference to round-off (hence a single
1e-3 rtol catches a wrong-vehicle or wrong-path mistake by orders of
magnitude).

The agent's friction log (tool errors, confusing parameters,
workarounds) is printed with each case; feed recurring items into
`docs/FEATURE_BACKLOG.md`.
