#!/usr/bin/env python3
"""Lane C agent eval: blind agent vs Lane A reference, scored automatically.

Stage 2 of Lane C parity coverage (stage 1 is the scripted in-process
suite in examples/tests/test_parity_lane_c.py). This harness launches a
real agent through the Claude Agent SDK, hands it only the Lane C task
requirements, restricts it to the omd MCP tools (no filesystem, no
Bash, no repo access), and compares the metrics it reports against the
Lane A reference scripts.

Requires the claude-agent-sdk package and the Claude Code CLI:

    uv run --with claude-agent-sdk \
        packages/omd/examples/agent_eval/eval_lane_c.py paraboloid

    # all cases
    uv run --with claude-agent-sdk \
        packages/omd/examples/agent_eval/eval_lane_c.py all

The agent must end its run with a fenced JSON report; the harness
parses it, scores each metric against Lane A, and exits nonzero on any
required-metric failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLES_DIR = HERE.parent
REPO_ROOT = EXAMPLES_DIR.parents[2]


# ---------------------------------------------------------------------------
# Case definitions
# ---------------------------------------------------------------------------


@dataclass
class Metric:
    key: str                # flat key the agent must report under "metrics"
    lane_a_module: str      # lane_a module whose run() provides the reference
    lane_a_key: str         # key in that run()'s return dict
    rtol: float
    required: bool = True   # False: missing value is a WARN, not a FAIL


@dataclass
class Case:
    example: str            # directory name under packages/omd/examples/
    prompt_file: str        # file under <example>/lane_c/
    metrics: list[Metric]
    # Extra requirements appended to the task (details the lane_c prompt
    # delegates to repo files a blind MCP-only agent cannot read).
    supplement: str = ""
    lane_a_modules: list[str] = field(init=False)

    def __post_init__(self):
        self.lane_a_modules = sorted({m.lane_a_module for m in self.metrics})


# Every case uses its example's *_open.prompt.md: the open prompts state the
# engineering goal and the physical inputs (geometry, mission profile, design
# point) but deliberately name no factory, slot provider, parameter key, or
# tool-call sequence -- the agent must discover the workflow from the server's
# own affordances (tool descriptions, omd://reference).
#
# ocp_pyc_coupled has an open prompt but is NOT scored here: its tool-surface
# path shares the Lane B materializer, whose weight-slot precedence forces an
# OEW passthrough (~8% OEW / ~4% fuel gap vs Lane A -- see the example's
# TODO.md), so an agent cannot match the Lane A reference through the tools.

def _ocp_metrics(module: str) -> list[Metric]:
    return [
        Metric("fuel_burn_kg", module, "fuel_burn_kg", rtol=1e-3),
        Metric("OEW_kg", module, "OEW_kg", rtol=1e-3),
        Metric("MTOW_kg", module, "MTOW_kg", rtol=1e-6),
    ]


CASES: dict[str, Case] = {
    "paraboloid": Case(
        example="paraboloid",
        prompt_file="all_open.prompt.md",
        metrics=[
            Metric("analysis_f_xy", "analysis", "f_xy", rtol=1e-6),
            Metric("opt_f_xy", "optimization", "f_xy", rtol=1e-4),
            # DV retrieval through the tool surface is a known gap
            # (FEATURE_BACKLOG); score but do not fail on these.
            Metric("opt_x", "optimization", "x", rtol=1e-3, required=False),
            Metric("opt_y", "optimization", "y", rtol=1e-3, required=False),
        ],
    ),
    "oas_aero_rect": Case(
        example="oas_aero_rect",
        prompt_file="aero_analysis_open.prompt.md",
        metrics=[
            Metric("CL", "aero_analysis", "CL", rtol=1e-6),
            Metric("CD", "aero_analysis", "CD", rtol=1e-6),
        ],
    ),
    # 1e-4 leaves headroom for the agent's coupled-solver tolerance choice;
    # a wrong mesh or condition still misses by orders of magnitude.
    "oas_aerostruct_rect": Case(
        example="oas_aerostruct_rect",
        prompt_file="aerostruct_analysis_open.prompt.md",
        metrics=[
            Metric("CL", "aerostruct_analysis", "CL", rtol=1e-4),
            Metric("CD", "aerostruct_analysis", "CD", rtol=1e-4),
        ],
    ),
    "ocp_caravan_basic": Case(
        example="ocp_caravan_basic",
        prompt_file="basic_mission_open.prompt.md",
        metrics=_ocp_metrics("basic_mission"),
    ),
    "ocp_caravan_full": Case(
        example="ocp_caravan_full",
        prompt_file="full_mission_open.prompt.md",
        metrics=_ocp_metrics("full_mission"),
    ),
    "ocp_hybrid_twin": Case(
        example="ocp_hybrid_twin",
        prompt_file="hybrid_mission_open.prompt.md",
        metrics=_ocp_metrics("hybrid_mission"),
    ),
    "oas_ocp_combined": Case(
        example="oas_ocp_combined",
        prompt_file="wing_mission_open.prompt.md",
        metrics=[
            Metric("wing_CL", "wing_mission", "wing_CL", rtol=1e-6),
            Metric("wing_CD", "wing_mission", "wing_CD", rtol=1e-6),
            *_ocp_metrics("wing_mission"),
        ],
    ),
    "ocp_oas_coupled": Case(
        example="ocp_oas_coupled",
        prompt_file="coupled_mission_open.prompt.md",
        metrics=_ocp_metrics("coupled_mission"),
    ),
    "ocp_oas_direct": Case(
        example="ocp_oas_direct",
        prompt_file="direct_coupled_mission_open.prompt.md",
        metrics=_ocp_metrics("direct_coupled_mission"),
    ),
    "pyc_turbojet": Case(
        example="pyc_turbojet",
        prompt_file="turbojet_design_open.prompt.md",
        metrics=[
            Metric("Fn", "design_analysis", "Fn", rtol=1e-4),
            Metric("TSFC", "design_analysis", "TSFC", rtol=1e-4),
            Metric("OPR", "design_analysis", "OPR", rtol=1e-4),
        ],
    ),
    "ocp_three_tool": Case(
        example="ocp_three_tool",
        prompt_file="coupled_mission_open.prompt.md",
        metrics=_ocp_metrics("coupled_mission"),
    ),
    # Lane A loads the archer-midnight vehicle from its JSON config file; the
    # built-in template is vendored from that same file, so the template-built
    # result the blind agent can reach matches the file-based reference to
    # round-off.
    "evt_open_sizing": Case(
        example="evt_native_sizing",
        prompt_file="sizing_open.prompt.md",
        metrics=[
            Metric("sized_mtow_kg", "sizing", "sized_mtow_kg", rtol=1e-3),
            Metric("total_mission_energy_kw_hr", "sizing",
                   "total_mission_energy_kw_hr", rtol=1e-3),
            Metric("peak_power_kw", "sizing", "peak_power_kw", rtol=1e-3),
        ],
    ),
}


# ---------------------------------------------------------------------------
# Lane A references (one subprocess per example: shared.py modules collide
# when different examples are imported into the same process)
# ---------------------------------------------------------------------------


def lane_a_reference(example: str, module: str) -> dict:
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(EXAMPLES_DIR)!r})\n"
        f"from {example}.lane_a.{module} import run\n"
        "print(json.dumps(run(), default=float))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Lane A reference {example}.lane_a.{module} failed:\n{proc.stderr}"
        )
    return json.loads(proc.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

PREAMBLE = """\
You are an engineering analysis agent evaluating the omd MCP server.
Complete the task below using ONLY the omd MCP tools (mcp__omd__*).

HARD RULES:
- You have no filesystem, shell, or web access; work entirely through
  the tool workspace (relative paths resolve server-side).
- The task states the engineering goal, not the tool procedure. Work out
  the right calls and their order from the server's own affordances:
  tool descriptions, the omd://reference resource, and error messages.
- If a tool call fails, adapt and retry with corrected inputs.

--- TASK ---
"""

REPORT_FORMAT = """\

--- REPORT FORMAT ---
End your final message with exactly one fenced JSON block:

```json
{{
  "plan_id": "...",
  "run_id": "...",
  "status": "...",
  "metrics": {{{metric_keys}}},
  "friction": ["each tool error, confusing parameter, or workaround"]
}}
```

Report every metric at full precision (all digits the tools give you).
If a metric is not retrievable through the tools, set it to null and
explain in "friction". Do not round, do not omit keys.
"""


def build_prompt(case: Case) -> str:
    task = (EXAMPLES_DIR / case.example / "lane_c" / case.prompt_file).read_text()
    metric_keys = ", ".join(f'"{m.key}": <number>' for m in case.metrics)
    return (
        PREAMBLE + task + case.supplement
        + REPORT_FORMAT.format(metric_keys=metric_keys)
    )


# ---------------------------------------------------------------------------
# Agent run (Claude Agent SDK)
# ---------------------------------------------------------------------------


async def run_agent(prompt: str, data_root: Path, model: str | None,
                    max_turns: int, verbose: bool) -> tuple[str, float | None]:
    try:
        from claude_agent_sdk import (
            AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock,
            query,
        )
    except ImportError:
        sys.exit(
            "claude-agent-sdk is not installed. Run via:\n"
            "  uv run --with claude-agent-sdk "
            "packages/omd/examples/agent_eval/eval_lane_c.py <case>"
        )

    options = ClaudeAgentOptions(
        cwd=str(REPO_ROOT),
        model=model,
        max_turns=max_turns,
        permission_mode="bypassPermissions",
        mcp_servers={
            "omd": {
                "type": "stdio",
                "command": sys.executable,
                "args": ["-m", "hangar.omd.server"],
                "env": {
                    "OMD_DATA_ROOT": str(data_root / "omd_data"),
                    "OMD_DB_PATH": str(data_root / "analysis.db"),
                    "OMD_PLAN_STORE": str(data_root / "plans"),
                    "OMD_RECORDINGS_DIR": str(data_root / "recordings"),
                },
            },
        },
        allowed_tools=["mcp__omd"],
        disallowed_tools=[
            "Bash", "Read", "Write", "Edit", "Glob", "Grep",
            "WebFetch", "WebSearch", "Task", "NotebookEdit",
        ],
    )

    final_text, cost = "", None
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    final_text = block.text
                    if verbose:
                        print(f"  [agent] {block.text[:200]}", flush=True)
        elif isinstance(message, ResultMessage):
            if message.result:
                final_text = message.result
            cost = message.total_cost_usd
    return final_text, cost


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def extract_report(text: str) -> dict:
    blocks = re.findall(r"```(?:json)?\s*\n(\{.*?\})\s*\n```", text, re.DOTALL)
    for raw in reversed(blocks):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"No parseable JSON report in agent output:\n{text[-2000:]}")


def score_case(
    case: Case, report: dict, refs: dict[str, dict],
) -> tuple[bool, list[dict]]:
    metrics = report.get("metrics", {})
    print(f"\n  {'Metric':<16s} {'Lane A':>18s} {'Agent':>18s} "
          f"{'Rel err':>10s}  Verdict")
    print(f"  {'-' * 16} {'-' * 18} {'-' * 18} {'-' * 10}  {'-' * 7}")

    ok = True
    rows: list[dict] = []
    for m in case.metrics:
        ref = refs[m.lane_a_module][m.lane_a_key]
        got = metrics.get(m.key)
        if not isinstance(got, (int, float)):
            verdict = "FAIL" if m.required else "WARN"
            ok = ok and not m.required
            print(f"  {m.key:<16s} {ref:>18.10g} {str(got):>18s} "
                  f"{'n/a':>10s}  {verdict} (missing)")
            rows.append({"key": m.key, "lane_a": float(ref), "agent": None,
                         "rel_err": None, "rtol": m.rtol,
                         "required": m.required, "verdict": verdict})
            continue
        rel = abs(got - ref) / max(abs(ref), 1e-30)
        passed = rel <= m.rtol
        verdict = "PASS" if passed else ("FAIL" if m.required else "WARN")
        ok = ok and (passed or not m.required)
        print(f"  {m.key:<16s} {ref:>18.10g} {got:>18.10g} "
              f"{rel:>10.2e}  {verdict}")
        rows.append({"key": m.key, "lane_a": float(ref), "agent": float(got),
                     "rel_err": rel, "rtol": m.rtol,
                     "required": m.required, "verdict": verdict})

    friction = report.get("friction") or []
    if friction:
        print("\n  Friction log:")
        for item in friction:
            print(f"    - {item}")
    return ok, rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "cases", nargs="+",
        choices=[*CASES, "all"],
        help="Lane C cases to evaluate ('all' runs every case)",
    )
    parser.add_argument("--model", default=None,
                        help="Model override passed to the agent")
    parser.add_argument("--max-turns", type=int, default=80)
    parser.add_argument("--keep-data", action="store_true",
                        help="Keep the temp omd data root for inspection")
    parser.add_argument("--verbose", action="store_true",
                        help="Stream agent text while it works")
    parser.add_argument("--save-json", type=Path, default=None,
                        help="Write per-case scored results to this JSON file "
                             "(consumed by paper/make_tables.py)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip cases already present in --save-json "
                             "(reuse their saved rows)")
    args = parser.parse_args()

    names = list(CASES) if "all" in args.cases else list(dict.fromkeys(args.cases))
    all_ok = True
    saved: list[dict] = []

    if args.resume and args.save_json and args.save_json.exists():
        saved = json.loads(args.save_json.read_text())
        done = {row["case"] for row in saved}
        skipped = [n for n in names if n in done]
        names = [n for n in names if n not in done]
        all_ok = all(row.get("ok") for row in saved)
        if skipped:
            print(f"Resuming: reusing saved results for {', '.join(skipped)}")

    def _checkpoint() -> None:
        if args.save_json:
            args.save_json.parent.mkdir(parents=True, exist_ok=True)
            args.save_json.write_text(json.dumps(saved, indent=2) + "\n")

    for name in names:
        case = CASES[name]
        print(f"\n{'=' * 70}\nLane C agent eval: {name}\n{'=' * 70}")

        print("  Computing Lane A references...")
        refs = {mod: lane_a_reference(case.example, mod)
                for mod in case.lane_a_modules}

        tmp = Path(tempfile.mkdtemp(prefix=f"lane_c_eval_{name}_"))
        print(f"  omd data root: {tmp}")
        print("  Running blind agent (omd MCP tools only)...")
        try:
            text, cost = await run_agent(
                build_prompt(case), tmp, args.model, args.max_turns,
                args.verbose,
            )
        except Exception as exc:  # noqa: BLE001 - SDK/CLI errors must not
            # kill the remaining cases; record and move on.
            print(f"  ERROR: agent run failed: {exc}")
            all_ok = False
            saved.append({"case": name, "model": args.model, "ok": False,
                          "error": f"agent run failed: {exc}",
                          "cost_usd": None, "metrics": []})
            _checkpoint()
            continue
        if cost is not None:
            print(f"  Agent cost: ${cost:.4f}")

        try:
            report = extract_report(text)
        except ValueError as exc:
            print(f"  FAIL: {exc}")
            all_ok = False
            saved.append({"case": name, "model": args.model, "ok": False,
                          "error": str(exc), "cost_usd": cost, "metrics": []})
            _checkpoint()
            continue

        print(f"  plan_id={report.get('plan_id')}  "
              f"run_id={report.get('run_id')}  status={report.get('status')}")
        ok, rows = score_case(case, report, refs)
        all_ok = all_ok and ok
        print(f"\n  Case result: {'PASS' if ok else 'FAIL'}")
        saved.append({
            "case": name, "model": args.model, "ok": ok,
            "plan_id": report.get("plan_id"), "run_id": report.get("run_id"),
            "status": report.get("status"), "cost_usd": cost,
            "friction": report.get("friction") or [], "metrics": rows,
        })
        _checkpoint()

        if not args.keep_data:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    if args.save_json:
        _checkpoint()
        print(f"\nSaved scored results to {args.save_json}")

    print(f"\n{'=' * 70}\nOverall: {'PASS' if all_ok else 'FAIL'}\n{'=' * 70}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
