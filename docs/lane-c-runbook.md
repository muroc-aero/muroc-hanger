# Lane C runbook

Copy-pasteable steps for every way Lane C runs today, from the scripted
parity suite up to sandboxed local-model evals. Every step is a
non-interactive shell command, so the runbook works the same whether a
human or an agent is driving.

Background reading (not required to run anything):

- `docs/parity-lanes-and-agent-eval.md` -- what the lanes are and why
- `paper/README.md` -- what the paper harness produces
- `packages/omd/examples/agent_eval/README.md` -- the blind-agent harness
- sibling `hangar-evals/README.md` and `hangar-evals/notes/llm-eval-plan.md`
  -- the sandboxed model x harness matrix

Three paths, in increasing infrastructure order:

| Path | What runs | Repo | Needs |
|------|-----------|------|-------|
| A | scripted lanes A/B/C + the live-agent Lane C column | the-hangar | dev setup; Claude Code CLI for the agent column |
| B | model x harness eval cells (anchor, sandboxed, local models) | hangar-evals | path A's setup + hangar-evals install; Docker/Ollama per arm |
| C | a governed study over eval cells | have-agent | paths A+B plus the eval bridge (planned -- see below) |

All the-hangar commands run from the the-hangar repo root; all
hangar-evals commands from the hangar-evals repo root.

## Path A -- the-hangar only

### A0. One-time setup

```bash
bash scripts/dev-setup.sh          # clones pinned upstreams, installs all packages
```

For the agent column (A2) you also need the Claude Code CLI installed and
authenticated (`claude` on PATH; run `claude` once interactively to log in).

### A1. Scripted lanes A/B/C -> paper table

```bash
uv run python paper/run_lanes.py --quick    # paraboloid-only smoke, ~1 min
uv run python paper/run_lanes.py            # full suite (slow tests included)
uv run python paper/make_tables.py
```

Outputs: `paper/results/lane_parity.jsonl` (+ `lane_parity_meta.json`) and
`paper/tables/lane_parity.{csv,md,tex}`. Useful flags on `run_lanes.py`:
`--lanes ab|c|all`, `-k <pytest expr>`, `--include-known-gaps`.

To run the scripted Lane C suite directly (no table recording):

```bash
uv run pytest packages/omd/examples/tests/test_parity_lane_c.py -v -s -m "not slow"
```

### A2. Live-agent Lane C column (optional, needs Claude credentials)

```bash
# one case, watching the agent work
uv run --with claude-agent-sdk \
    packages/omd/examples/agent_eval/eval_lane_c.py paraboloid --verbose

# all cases -> the "Lane C (agent)" table columns
uv run --with claude-agent-sdk \
    packages/omd/examples/agent_eval/eval_lane_c.py all \
    --save-json paper/results/lane_c_agent.json
uv run python paper/make_tables.py          # agent columns appear automatically
```

Other flags: `--model <name>`, `--max-turns N` (default 80), `--keep-data`
(keep the temp omd data root), `--resume` (skip cases already in
`--save-json`). Exit code is nonzero if any required metric fails.

## Path B -- hangar-evals (model x harness matrix)

hangar-evals reads the same open prompts and Lane A references live from
this repo through the `HANGAR_REPO` seam (default: sibling `../the-hangar`).
It never vendors case content -- the-hangar stays the single source of truth.

### B0. One-time setup

```bash
cd ../hangar-evals
uv pip install -e ".[dev]"          # base + tests
uv pip install -e ".[anchor]"       # only for the Claude anchor arm
export HANGAR_REPO=../the-hangar    # only if not the sibling default
```

The Python environment must also have the-hangar's packages importable
(Lane A references run under `sys.executable`); installing hangar-evals
into the-hangar's venv, or the-hangar editable into hangar-evals' venv,
both work.

Per-arm extras:

- **Anchor (hosted Claude):** Claude Code CLI authenticated, as in path A.
- **Sandboxed arms:** Docker (colima works), plus the pinned images -- the
  exact `docker build` lines are in the headers of
  `containers/anchor.Dockerfile` and `containers/opencode.Dockerfile`.
  The sandboxed anchor authenticates via `CLAUDE_CODE_OAUTH_TOKEN`
  (mint one with `claude setup-token`).
- **Local models (OpenCode arm):** `opencode` CLI installed and Ollama
  serving on `http://localhost:11434` with the model pulled.

### B1. Validity baselines first

Before trusting any agent scores, confirm the tasks are achievable through
the tool surface at all (scripted MCP-call baselines, no agent):

```bash
python -m hangar.evals.validity --all               # or --case <name>
# -> results/validity/validity_<stamp>.json ; expect every case VALID
```

### B2. Run eval cells

Manifests in `configs/` are the reproducible way to run; every knob also
exists as a flag (`python -m hangar.evals.run --help` lists cases and
harnesses).

```bash
# anchor, stdio omd server (simplest end-to-end check)
python -m hangar.evals.run --config configs/paraboloid_claude.json

# anchor, container-sandboxed over http (needs Docker + CLAUDE_CODE_OAUTH_TOKEN)
python -m hangar.evals.run --config configs/paraboloid_claude_sandbox.json

# local model via OpenCode, sandboxed (needs Docker + Ollama)
python -m hangar.evals.run --config configs/paraboloid_opencode_sandbox.json

# ad hoc: any case x harness x model, multi-seed
python -m hangar.evals.run --case oas_aero_rect --harness claude --seeds 3
python -m hangar.evals.run --case paraboloid --harness opencode --model qwen3:8b --seeds 5
```

Each run writes three siblings under `results/`:
`<case>_<stamp>.jsonl` (per-seed records), `<case>_<stamp>_config.json`
(manifest + observed environment, including both repos' git SHAs), and
`<case>_<stamp>_summary.json` (cell summaries: pass rate, pass@k, tool-use
stats). Seeds flush as they finish; after a crash or Ctrl-C:

```bash
python -m hangar.evals.run --resume results/<case>_<stamp>.jsonl
```

Grading is effect-based: the primary verdict reads the run's own omd
`analysis.db`, not the agent's self-report, so an agent cannot pass by
reporting numbers it never produced.

### B3. Feed the paper table

`paper/make_tables.py` picks up `*_summary.json` from the sibling
hangar-evals results dir automatically (`--evals-dir` to override) and
renders `paper/tables/sandboxed_evals.{csv,md,tex}`, keeping the latest
summary per (case, harness, model):

```bash
cd ../the-hangar
uv run python paper/make_tables.py
```

### Repeatability caveat

Evals read the live the-hangar working tree. Don't switch branches or edit
case content mid-sweep; the `_config.json` environment block records both
repos' git SHAs and dirty flags -- check it before citing numbers.

## Path C -- a have-agent study over eval cells (planned)

The sibling `have-agent` repo is a study substrate: a StudyRequest YAML is
decomposed into ANALYSIS+CHECK jobs in SQLite, pull workers execute them
through a pluggable `Executor`, a `CheckSuite` issues pass/warn/fail
verdicts, policy auto-accepts clean cases and routes the rest to a human
review inbox, and a REPORT job publishes a markdown briefing. It already
runs omd *plan* studies against this repo today (`--executor hangar`; see
have-agent's README, "Real runs against the-hangar").

Running *eval* cells (path B) under a have-agent study needs a small
bridge that does not exist yet:

1. **have-agent:** accept a dotted-path executor/check-suite alongside the
   built-in `fake`/`hangar` choices.
2. **hangar-evals:** a `have_bridge` module -- an `Executor` that runs one
   eval seed per job via `run_cell` (job payload: case, harness, model,
   seed) and a `CheckSuite` that folds the graded record into a
   pass/warn/fail verdict -- plus an example StudyRequest whose `cases:`
   list enumerates the case x harness x model x seed cells.

The intended flow, once the bridge lands (commands illustrative until then):

```bash
cd ../have-agent
uv run have --db muroc.db submit examples/lane_c_eval.yaml
uv run have --db muroc.db approve <study_id>
uv run --project ../the-hangar --with ../have-agent --with ../hangar-evals \
  have --db muroc.db worker run --id worker:evals-1 \
  --executor hangar.evals.have_bridge:make_executor
uv run have --db muroc.db status <study_id>
uv run have --db muroc.db report <study_id>
```

The bridge executor keeps writing standard hangar-evals results files, so
path B3 (the paper table) is unchanged -- have-agent adds leases, retries,
gating, the review inbox, and the study briefing on top without becoming a
second source of truth for scores.
