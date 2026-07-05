# The omd analysis plan: a declarative front-end for OpenMDAO (plans, studies, and how it runs)

**Audience:** (1) new developers getting up to speed on what `omd` is, how a plan
becomes a running OpenMDAO problem, and how studies sweep many cases; and (2) the
authors of the-hangar paper who need a precise, citable account of the plan/study
design, its relationship to prior work, and where it is distinct.

**Companion doc:** provenance is covered separately in
[`provenance-and-capture-tool.md`](./provenance-and-capture-tool.md). This doc
references provenance where it touches plans/studies but does not re-derive it.
The multi-case *operational* guide is [`STUDIES.md`](./STUDIES.md); this doc is
the architectural/positioning account.

---

## 1. TL;DR — what omd is

`omd` (package `hangar-omd`, Python namespace `hangar.omd`) is a **general-purpose,
declarative plan runner for [OpenMDAO](https://openmdao.org)**. Instead of writing
a Python script that assembles an OpenMDAO `Problem`, wires design variables,
constraints, an objective, solvers, and a driver, you write a **YAML analysis
plan**. omd:

1. **validates** the plan against a JSON Schema plus a semantic preflight
   (typo suggestions on DV/constraint/objective names),
2. **materializes** it into a live `om.Problem` via a **factory registry**
   (each component type knows how to build its OpenMDAO subsystem),
3. **runs** it (`run_model` for analysis, `run_driver` for optimization),
4. **records** results with W3C-PROV-shaped provenance, an OpenMDAO
   `SqliteRecorder` iteration history, an N2 diagram, and factory-aware plots,
5. and exposes the *same* surface over a CLI (`omd-cli`) and an MCP server
   (`hangar.omd.server`) so a human or an **AI agent** can author, validate, run,
   and interpret plans identically.

A **study** is the multi-case layer on top: one `study.yaml` expands (DOE matrix +
manual cases) into many plan runs, checkpointed and resumable, with 2-axis trade
grids rendered from the aggregated case table.

The one-sentence framing for the paper: **omd turns an OpenMDAO MDAO problem into a
declarative, schema-validated, provenance-tracked, agent-authorable artifact — and
a study turns a design sweep into a resumable, reviewable one.**

---

## 2. The plan artifact — anatomy of a plan.yaml

The schema is the contract. It lives in one place and is the authoritative
description of what a plan may contain:

- **Schema + validation:** `packages/omd/src/hangar/omd/plan_schema.py`
  (`PLAN_SCHEMA`, `validate_plan`, `load_and_validate`). It is a
  [JSON Schema draft 2020-12](https://json-schema.org/) document with
  `additionalProperties: false` almost everywhere, so an unknown key is an error,
  not a silent no-op. A relaxed `PLAN_SCHEMA_PARTIAL` (`validate_partial`) lets the
  interactive builder validate in-progress plans without failing on
  not-yet-authored sections.

Only two top-level keys are **required**: `metadata` and `components`. Everything
else is optional and additive. The full vocabulary:

| Section | Required | Purpose |
|---|---|---|
| `metadata` | ✅ | `id`, `name`, `version` (+ `description`, `content_hash`, `parent_version`, and study stamps `study`/`case_id`) |
| `components` | ✅ | list of `{id, type, config}` — each `type` names a **factory** (e.g. `oas/AeroPoint`, `ocp/BasicMission`, `pyc/TurbojetDesign`, `evt/Sizing`, `paraboloid/Paraboloid`); `config` is factory-specific and may declare `slots` (composable sub-models) |
| `operating_points` | | flight/analysis conditions — either a flat dict (single point) or `{flight_points: [...], shared: {...}}` (multipoint). Values may be bare numbers/arrays or `{value, units}` unit-tagged objects |
| `design_variables` | | `[{name, lower, upper, units, scaler/ref/ref0, initial, traces_to}]` — short names (`twist_cp`, `CL`) resolved to full OpenMDAO paths by the materializer |
| `constraints` | | `[{name, upper/lower/equals, scaler, units, point, traces_to}]` |
| `objective` | | `{name, scaler, units, traces_to}` |
| `optimizer` | | `{type: SLSQP/…, options: {...}}` |
| `solvers` | | one solver scope or a list of scopes: `{target, nonlinear: {type, options}, linear: {type, options}}` |
| `connections` | | explicit `{src, tgt}` edges between components |
| `shared_vars` | | `{name, value, units, consumers[], rationale}` — one value fanned out to multiple components |
| `composition_policy` | | `explicit` or `auto` (auto-derive shared vars across components) + `no_auto_share` opt-outs |
| `initial_values` | | plan-level post-`setup()` value overrides (warm starts) for arbitrary paths |
| `requirements` | | first-class `{id, text, type, acceptance_criteria[{metric, comparator, threshold/range, units}], verification, priority, status, traces_to}` |
| `decisions` | | first-class design rationale `{decision, reason, stage, agent, alternatives_considered[{option, rejected_because}], references, element_path}` |
| `rationale` | | free-form narrative bullets |
| `analysis_plan` | | a *plan-of-analysis*: `{strategy, phases[{id, mode, depends_on, success_criteria, checks}], replan_triggers}` |

Two things in that table are the point of the whole design, and worth calling out
for the paper:

- **Requirements, decisions, and an analysis_plan are first-class plan content**,
  not comments. `acceptance_criteria` are machine-checkable (`metric comparator
  threshold`), so a run can be *judged* against the plan automatically
  (`record_conclusion`, `run.py:_compare` / `_record_assessment`). `decisions`
  carry `alternatives_considered` with `rejected_because` — the plan records *why*
  a formulation was chosen, not just what it is. This is design-rationale capture
  embedded in the executable artifact.
- **Short-name resolution.** A user writes `objective: {name: CD}` or
  `design_variables: [{name: twist_cp}]`; the materializer
  (`materializer.py:_resolve_var_path`) maps those to the real OpenMDAO paths
  (`aero_point_0.wing_perf.CD`, `wing.twist_cp`) using factory-supplied
  `var_paths`. The plan stays legible and tool-agnostic; the wiring is derived.

### 2.1 A minimal plan (paraboloid optimization)

`packages/omd/examples/paraboloid/lane_b/optimization/plan.yaml`:

```yaml
metadata: {id: ex-paraboloid-opt, name: Paraboloid optimization example, version: 1}
operating_points: {x: 0.0, y: 0.0}
design_variables:
  - {name: x, lower: -50.0, upper: 50.0}
  - {name: y, lower: -50.0, upper: 50.0}
objective: {name: paraboloid.f_xy}
optimizer: {type: SLSQP, options: {maxiter: 50}}
components:
  - {id: paraboloid, type: paraboloid/Paraboloid, config: {}}
```

### 2.2 A cross-tool plan (OpenConcept mission with an OAS drag slot)

`packages/omd/examples/ocp_oas_coupled/lane_b/coupled_mission/plan.yaml` shows the
**slot** mechanism — one component's model has named holes another tool fills:

```yaml
components:
  - id: mission
    type: ocp/BasicMission
    config:
      aircraft_template: caravan
      architecture: turboprop
      num_nodes: 11
      solver_settings: {solver_type: newton, maxiter: 20, atol: 1.0e-10, rtol: 1.0e-10}
      mission_params: {cruise_altitude_ft: 18000.0, mission_range_NM: 250.0, ...}
      slots:
        drag:
          provider: oas/vlm           # OAS VLM replaces OpenConcept's PolarDrag
          config: {num_x: 2, num_y: 7, num_twist: 4}
```

Slots are how omd composes the leaf tools (OAS + OpenConcept + pyCycle) into one
OpenMDAO model without hand-wiring. Providers declare `design_variables` and
`result_paths` that the materializer resolves for optimization and result
extraction. See `packages/omd/CLAUDE.md` (§"pyCycle-OCP slot providers",
§"Slot provider design variables") for the full slot catalog.

---

## 3. Two ways to author a plan

### 3.1 Modular directory + assemble

A plan can be authored as a **directory of small YAML files** and merged into one
canonical `plan.yaml`:

- `assemble.py:_merge_yaml_files` maps `metadata.yaml`, `requirements.yaml`,
  `operating_points.yaml`, `connections.yaml`, `solvers.yaml`, `decisions.yaml`,
  `rationale.yaml`, `optimization.yaml` (which promotes `design_variables` /
  `constraints` / `objective` / `optimizer` to top level), and every file under
  `components/*.yaml` (collected into the components array).
- `assemble.py:assemble_plan` then computes a **content hash**, allocates a
  **version** (`plans/{plan-id}/v{N}.yaml` in the plan store), and records the
  plan's requirements, decisions, and analysis_plan into the provenance DB.

CLI: `omd-cli assemble my-plan/`, plus incremental builders
`omd-cli plan init/add-component/add-dv/add-requirement/… ` and
`omd-cli plan review`.

### 3.2 Builder tools / direct YAML (agent path)

Over MCP an agent uses the builder tools (`plan_init` → `plan_add_component` →
`plan_set_operating_point` → `plan_add_dv` → `plan_set_objective` →
`assemble_plan`) or writes YAML directly (`write_plan` / `read_plan`). Relative
paths resolve into a **per-user server-side workspace**
(`hangar_data/omd/workspace/{user}`), so an agent with no filesystem access
(e.g. claude.ai) can author, run, and read plans entirely through tool calls. The
tool surface is 1:1 with the CLI — the CLI and MCP tool both call the same
implementation (`packages/omd/src/hangar/omd/tools/`).

---

## 4. How a plan runs — materialize → execute → record

Data flow (from `packages/omd/CLAUDE.md`):

```
plan.yaml ─ load_and_validate() ─ materialize() ─ prob.run_driver/run_model()
                                       │                      │
                                  factory builds        OpenMDAO writes to
                                  om.Problem            SqliteRecorder (.sql)
                                       │                      │
                                  prob.setup()          recorder iteration data
                                       │
                                  _generate_n2() ──▶ n2/{run_id}.html
```

### 4.1 Entry point: `run_plan`

`run.py:run_plan(plan_path, mode, recording_level, …)` is the pipeline:

1. **Load + validate** (`load_and_validate`); schema errors abort before compute.
2. **Idempotency / study bookkeeping.** When called with `(study_id, case_id,
   attempt)` the run is idempotent on that triple — a repeat returns the stored
   result instead of recomputing. `overrides` (dotted-path patches) and
   `warm_start_run` (seed `design_variables[].initial` from a prior run's final
   case) are applied here.
3. **Materialize** (`materializer.py:materialize`): factory lookup, solver/driver
   configuration, DV/constraint/objective registration, recorder attachment.
4. **Execute** under a wall-clock timeout: `run_model()` (analysis) or
   `run_driver()` (optimize).
5. **Extract a summary** (factory-family-aware: OAS, OCP profiles, evt, pyc,
   composite slots), **generate the N2**, **record** entities/activities/edges and
   an assessment against the plan's requirements.

Return is a structured dict: `run_id`, `status`
(`converged`/`failed`/`completed`/`timeout`), `summary`, `errors`.

### 4.2 The materializer

`materializer.py:materialize` is the heart of the declarative→imperative
translation:

- **Single component:** the one factory builds the whole `om.Problem`.
- **Multiple components:** `_materialize_composite` builds each, extracts its inner
  model as a named subsystem, and wires `connections` / `shared_vars` (or
  auto-derives shared vars when `composition_policy: auto`).
- **Solvers** (`_configure_solvers`) apply per-scope nonlinear/linear solver specs
  to `target` subsystems; **driver** (`_configure_driver`) sets the optimizer and
  registers DVs/constraints/objective, resolving short names via
  `_resolve_var_path`.
- `setup()` is called *after* factories return (factories build but must not
  `setup()` — the exception is model-is-root factories like pyCycle that set
  `_setup_done`). Complex-step components (native evt) get `force_alloc_complex`.
- A **recorder** (`_configure_recorder`) attaches an OpenMDAO `SqliteRecorder` at
  the chosen `recording_level` (`minimal`/`driver`/`solver`/`full`). That `.sql`
  is the single source of truth for plots and convergence tables — never the
  analysis DB.

### 4.3 The factory registry

`registry.py` maps a component `type` string to a builder
`(component_config, operating_points) -> (om.Problem, metadata)` and to a plot
provider. Builders live in `factories/` (`oas.py`, `oas_aero.py`, `pyc.py`,
`evt.py`, `paraboloid.py`); each registers under a `try/except ImportError` guard
so omd degrades gracefully where an upstream solver is not installed. Metadata keys
(`point_name`, `output_names`, `var_paths`, `initial_values`,
`component_family`, …) are the contract the run/plot layers read — the full table
is in `packages/omd/CLAUDE.md` §"Factory metadata keys".

### 4.4 Outputs of a run

- **Provenance DB** (`analysis.db`): entities/activities/`prov_edges`, `run_cases`.
  See [`provenance-and-capture-tool.md`](./provenance-and-capture-tool.md) §3.
- **Recorder** (`recordings/{run_id}.sql`): full iteration history.
- **N2** (`n2/{run_id}.html`): interactive model/DSM diagram, generated while the
  `Problem` is live.
- **Plots** (`plots/{run_id}/*.png`): factory-aware, rendered on demand from the
  recorder via `CaseReader` (`plotting/`).
- **HTML run summary** and a **conclusion** (`record_conclusion`) that judges the
  run against the plan's `acceptance_criteria`.
- **Standalone Python export** (`export.py`, `omd-cli export`): regenerates a
  plain OpenMDAO script from the plan — an escape hatch from the declarative layer
  back to editable code, and a reproducibility artifact.

---

## 5. Studies — the multi-case layer

A **study** groups many cases (each case = one plan run) under one `study.yaml`.
The core is tool-independent (`packages/sdk/src/hangar/sdk/study/`); the omd
adapter is `packages/omd/src/hangar/omd/study_runner.py`. The operational guide is
[`STUDIES.md`](./STUDIES.md); the essentials:

### 5.1 The study spec

```yaml
metadata: {id: demo-oas-trade, name: "…", version: 1}
defaults:
  runner: omd
  spec: {plan: ../plan/base_plan.yaml, mode: analysis, timeout_seconds: 600}
cases:
  - matrix:                                  # DOE-style cartesian expansion
      id_template: "b{span_m:g}-a{alpha_deg:g}"
      axes:
        span_m:    {linspace: [8.0, 14.0, 4]}
        alpha_deg: {linspace: [2.0, 8.0, 4]}
      bind:                                  # every axis binds to ≥1 plan path
        span_m:    [components[wing].config.surfaces[wing].span]
        alpha_deg: [operating_points.alpha]
  - case: {id: reference, params: {...}, spec: {...}}   # manual insertion
execution: {workers: 2, est_case_seconds: 30, review_threshold: 16, guard_max_cases: 64}
outputs:
  - {name: CL, path: AS_point_0.CL}          # runner-interpreted result paths
  - {name: CD, path: AS_point_0.CD}
```

(`packages/omd/demos/oas_trade/study/trade_study.yaml` is the runnable example;
the 133-case `demos/brelje_2018a/study/fig5_study.yaml` is the reference-grade MDO
grid.)

### 5.2 How a case runs

`study_runner.py:run_case` → `generate_case` writes a real, reviewable case
`plan.yaml` (the base plan with the case's axis bindings patched in via dotted-path
`set`), stamped with `metadata.study`/`metadata.case_id` and semantically validated
at generate time (so a typo fails *before* compute). It then calls the ordinary
`run_plan`, extracts the declared `outputs` from the run, and records a `partOf`
provenance edge to the study entity. Cross-tool studies mix runners per case
(`runner: oas|ocp|pyc|omd`) via the `hangar.study_runners` entry-point group.

### 5.3 The design decisions that make it reviewable (paper-relevant)

- **Review-first, blowup-guarded.** Expansion hard-fails past `guard_max_cases`;
  `run` refuses more pending cases than `review_threshold` without `--yes`. The MCP
  `run_study` *always* requires a `max_cases` (1–25) pilot batch — an agent is
  structurally forced into review → pilot → continue rather than launching a
  1000-cell sweep blind.
- **Checkpoint-first, resumable.** Every case completion is written to
  `state.json` + `cases.csv` before the next case. Resume is keyed by a
  deterministic `case_key` (hash of runner+spec+params): editing one case re-runs
  exactly the cases the edit touched; removed cases keep their history flagged
  `in_spec: false`.
- **Real artifacts.** Generated case plans are inspectable YAML on disk, copied
  into the plan store at run time — a study is a directory of ordinary plan runs,
  not an opaque sweep.
- **Sharpening estimates.** The review wall-time estimate starts from
  `est_case_seconds` and switches to the observed mean once cases complete.

### 5.4 Trade grids

`study_plots.py:plot_study` renders 2-axis trade grids from the aggregated
`cases.csv` (pcolormesh `style=paper` or contourf `style=contour`), masking
non-converged cells. Panel policy is dispatched per `component_type` through a
study-plot provider registry (`OAS_STUDY_PLOTS`, `OCP_STUDY_PLOTS`,
`PYC_STUDY_PLOTS`), with a generic one-panel-per-numeric-column fallback. The
mechanism is pandas-free (a columnar `Table` + numpy) and solver-free (reads
`cases.csv`, not a live problem), so grids render even where the upstream solver is
absent.

---

## 6. The two-surface (CLI + MCP) design, and why it matters for the paper

The same implementation backs both `omd-cli` and the FastMCP server
(`server.py`). Every MCP tool calls the identical function the CLI subcommand
calls. This is the mechanism behind the paper's central claim that an **AI agent
can drive real MDAO**: the agent is not given a bespoke, dumbed-down API; it gets
the exact plan-authoring, validation, execution, results, and provenance surface a
human engineer uses, over MCP, with:

- **Schema + semantic validation as a guardrail** (`validate_plan`): unknown/typo
  DV names are rejected with suggestions before any compute is spent — directly
  addressing the known OAS failure mode where unrecognized DV names are *silently
  ignored*.
- **Review gates on studies** that force the pilot-batch loop.
- **Provenance + decisions** so an agent's formulation choices and their rationale
  are recorded and auditable.

See `packages/omd/CLAUDE.md` §"MCP server" and the `hangar-mcp-guide` /
`omd-cli-guide` skills.

---

## 7. Related work and how omd differs

omd's distinguishing bundle is five things at once: **(a)** a declarative, *tool-agnostic*
YAML plan built from a **factory registry** that composes heterogeneous engineering
codes (OAS, OpenConcept, pyCycle, evt) into one OpenMDAO problem; **(b)** a
materializer that runs it with SQLite recording; **(c)** PROV-style provenance that
treats **decisions/rationale as first-class**; **(d)** an **MCP surface** that makes
the whole author→validate→run→inspect→study loop agent-native; and **(e)** a
resumable, review-gated **DOE study layer** over whole plan runs. Every ingredient
has prior art; the *combination* does not appear to exist as a single system in the
surveyed literature. Below, the closest analogues per area and how omd differs.

> URL-confidence note: the OpenMDAO/Aviary/WISDEM/windIO/GEMSEO/OAS/OpenConcept/Dakota
> links and the arXiv IDs for PROV-AGENT (2508.02866), the LLM MDO Agent (2511.17511),
> and OptiMUS (2310.06116) were verified during research. Treat as *unverified, check
> before citing*: the exact NL4Opt arXiv URL, the DUCTILE arXiv ID, pyDOE3's canonical
> repo, and the SUAVE→RCAIDE rename.

### 7.1 Declarative / config-driven MDAO specification

| Project | What it is | URL |
|---|---|---|
| **OpenMDAO** | The base framework omd targets; pure imperative Python API + `SqliteRecorder`. No first-class declarative front-end — the gap omd fills. | https://openmdao.org |
| **NASA Aviary** | Aircraft design on OpenMDAO with a CSV input deck + a `phase_info` Python-dict describing mission phases. The closest "input deck describes an OpenMDAO problem" analogue. | https://github.com/OpenMDAO/Aviary |
| **WISDEM/WEIS + windIO** | NREL wind-turbine MDAO driven by three YAML files validated against the **windIO** ontology (IEA Wind Task 37). The strongest existing "schema-validated YAML → OpenMDAO" example. | https://github.com/WISDEM/WISDEM · https://github.com/IEAWindSystems/windIO |
| **GEMSEO** | MDO framework with a `Scenario`/formulation/design-space abstraction and auto-assembly from a dependency graph. Declarative in spirit, configured via Python objects. | https://gemseo.readthedocs.io |
| **Dymos** | OpenMDAO trajectory optimization; phases/transcriptions via Python API (Aviary's `phase_info` serializes it). | https://github.com/OpenMDAO/dymos |

**Closest existing thing:** **WISDEM/WEIS + windIO** (validated YAML → OpenMDAO
optimization), runner-up **Aviary's deck + `phase_info`**. **How omd differs:**
windIO is a domain *data* ontology (turbine geometry) and Aviary is single-domain
(aircraft); neither has a **factory registry that composes heterogeneous external
tools** into one plan, per-scope solver/optimizer blocks over an arbitrary component
graph, decisions/rationale entities, or agent-authoring. omd generalizes the
"YAML → OpenMDAO" idea to a tool-agnostic plan and adds the provenance and agent
surfaces.

### 7.2 Provenance in computational workflows

| Project | What it is | URL |
|---|---|---|
| **W3C PROV** | The Entity/Activity/Agent data model omd's graph follows. | https://www.w3.org/TR/prov-overview/ |
| **PROV-AGENT** (Souza et al., IEEE e-Science 2025) | Extends W3C PROV to capture AI-agent prompts/responses/**decisions** across a workflow, explicitly over **MCP**. Strikingly close to omd's "agent + PROV + MCP + decisions". | https://arxiv.org/abs/2508.02866 |
| **ProvONE** | DataONE PROV extension for scientific-workflow provenance (prospective + retrospective). | https://purl.dataone.org/provone-v1-dev |
| **Pegasus / Kepler / Galaxy / Snakemake** | Workflow systems with data-lineage/provenance capture. | https://pegasus.isi.edu · https://snakemake.github.io |
| **IBIS / QOC / DRL** | Design-rationale tradition — decisions, alternatives, argumentation as first-class objects, historically *separate* from computational provenance. | https://en.wikipedia.org/wiki/Design_rationale |

**Closest existing thing:** **PROV-AGENT** (PROV + MCP + agent decisions). **How omd
differs:** PROV-AGENT is a general observability model for agentic workflows; omd
embeds provenance *inside* an MDAO plan runner and ties decisions to concrete plan
entities (a DV, an objective, a run) plus recorder `.sql` and N2 artifacts. And omd
unifies two usually-separate worlds — computational provenance and **IBIS-style
design rationale** — by recording *why this DV / why this bound* (with
`alternatives_considered` / `rejected_because`) welded to the executable plan. That
fusion is uncommon. (Full account: [`provenance-and-capture-tool.md`](./provenance-and-capture-tool.md),
which already documents omd's relationship to PROV-AGENT in depth.)

### 7.3 DOE-driven multi-case studies

| Project | What it is | URL |
|---|---|---|
| **OpenMDAO `DOEDriver`** | Native DOE driver (FullFactorial/LHS/Box-Behnken via pyDOE3), results to the recorder. The in-framework equivalent of omd's matrix. | https://openmdao.org/newdocs/versions/latest/features/building_blocks/drivers/doe_driver.html |
| **Dakota** (Sandia) | Input-deck-driven parameter studies / DOE / UQ / optimization, wrapping external sim executables as black boxes. | https://dakota.sandia.gov |
| **WISDEM DOE + `dakota_driver`** | YAML-configured DOE tutorial + an OpenMDAO↔Dakota bridge — the YAML-MDAO + DOE combination in the wild. | https://github.com/WISDEM/dakota_driver |
| **Ax / BoTorch** (Meta) | Adaptive experimentation / Bayesian-optimization with resumable multi-trial "experiment" state. | https://ax.dev |

**Closest existing thing:** **OpenMDAO `DOEDriver`** (DOE math + recorder) and
**Dakota** (deck-drives-studies pattern). **How omd differs:** `DOEDriver` varies DVs
*inside one live Problem*; omd studies expand a matrix over **arbitrary plan paths**,
each case a *full independent plan run*, with **deterministic case keys, checkpoint/
resume, review-before-run guards, and 2-axis trade-grid plots** — orchestration above
OpenMDAO, not a driver inside it. Dakota's resumability is job-restart, it wraps CLI
executables rather than materializing a native OpenMDAO problem, and it carries no
decisions/rationale provenance and no MCP surface.

### 7.4 LLM / AI-agent-driven engineering design

| Project | What it is | URL |
|---|---|---|
| **LLM-driven MDO Agent** (Guo et al., 2025) | LLM agent orchestrating NL-driven parametric CAD + RAG + FEA/optimization in a Designer/Modeler/Verifier/Optimizer loop. Closest published "LLM drives an MDO pipeline". | https://arxiv.org/abs/2511.17511 |
| **OptiMUS / NL4Opt / LM4OPT** | LLMs that translate NL into a formal (MI)LP model handed to a solver. The purest "LLM writes a declarative optimization spec a solver executes" — but in OR/MILP, not MDAO. | https://arxiv.org/abs/2310.06116 |
| **PROV-AGENT** | Agentic scientific workflows over MCP with provenance (see §7.2). | https://arxiv.org/abs/2508.02866 |
| **MCP-for-science servers** | MCP servers wrapping scientific/engineering tools for LLM agents (e.g. domain modeling agents, dynamic tool-sync architectures). | https://en.wikipedia.org/wiki/Model_Context_Protocol |

**Closest existing thing:** conceptually **OptiMUS/NL4Opt** ("LLM produces a
declarative optimization spec + preflight validation + executor") fused with the
domain scope of the **LLM MDO Agent (2511.17511)**. **How omd differs:** OptiMUS
targets textbook MILP (a single math model); omd's "solver" is a *coupled
multidisciplinary physics problem* assembled from engineering-tool factories with
operating points, per-scope nonlinear/linear solvers, and gradient drivers — and it
adds provenance-with-decisions and resumable studies that OR-modeling agents lack.
Unlike the CAD-centric MDO agents, omd cleanly separates **authoring a persistent,
inspectable, re-runnable plan artifact** from **running it**, and exposes that whole
lifecycle over MCP.

### 7.5 Novelty summary (for the paper)

No surveyed system combines: a tool-agnostic declarative MDAO plan + **factory
composition of heterogeneous external codes** + **rationale-aware PROV provenance** +
**agent-authorable via MCP** + a **resumable, review-gated declarative study layer**,
all over OpenMDAO. The nearest single reference points are WISDEM/windIO (§7.1),
PROV-AGENT (§7.2/§7.4), OpenMDAO `DOEDriver` / Dakota (§7.3), and OptiMUS + the LLM
MDO Agent (§7.4). Each ingredient is individually unremarkable; the union is the
contribution.

---

## 8. Code map — where to look

| Concern | File / symbol |
|---|---|
| Plan schema + validation | `packages/omd/src/hangar/omd/plan_schema.py` (`PLAN_SCHEMA`, `validate_plan`) |
| Semantic preflight (typo suggestions) | `plan_validate.py`, `plan_review.py` |
| Modular authoring / assemble / versioning | `assemble.py` (`_merge_yaml_files`, `assemble_plan`) |
| Incremental plan builder | `plan_mutate.py`, `omd-cli plan …` |
| Materialize (YAML → om.Problem) | `materializer.py` (`materialize`, `_materialize_composite`, `_resolve_var_path`, `_configure_solvers`, `_configure_driver`) |
| Run pipeline | `run.py` (`run_plan`, `_extract_summary`, `_record_assessment`, `record_conclusion`) |
| Factory registry | `registry.py`; builders in `factories/`, `evt/`, `pyc/` |
| Slot composition | `slots.py` |
| Recorder → DB import | `recorder.py`; DB in `db.py` |
| Standalone script export | `export.py` |
| Plots (per-run) | `plotting/` (factory-aware, reads recorder `.sql`) |
| Study core (tool-independent) | `packages/sdk/src/hangar/sdk/study/` |
| Study omd adapter | `packages/omd/src/hangar/omd/study_runner.py` |
| Study trade grids | `study_plots.py`, `plotting/_common.py` (`render_grid`) |
| MCP server | `server.py`; tools in `tools/` |
| Parameter reference (agent/human) | `packages/omd/src/hangar/omd/reference.md` (`omd://reference`) |
| Provenance (full account) | [`docs/provenance-and-capture-tool.md`](./provenance-and-capture-tool.md) |
| Studies (operational guide) | [`docs/STUDIES.md`](./STUDIES.md) |

### Try it

```bash
# Analysis / optimization from a plan
omd-cli run packages/omd/examples/paraboloid/lane_b/optimization/plan.yaml --mode optimize
omd-cli results <run_id> --summary
omd-cli plot <run_id> --type all

# A 2-axis trade study, review-first
omd-cli study review packages/omd/demos/oas_trade/study/trade_study.yaml
omd-cli study run    packages/omd/demos/oas_trade/study/trade_study.yaml --max-cases 4
omd-cli study run    packages/omd/demos/oas_trade/study/trade_study.yaml --yes
omd-cli study plot   demo-oas-trade --type trade_grid

# Escape hatch: regenerate a plain OpenMDAO script from a plan
omd-cli export packages/omd/examples/paraboloid/lane_b/optimization/plan.yaml -o script.py
```

---

## 9. Validation posture (the "lanes")

The plan pipeline is validated against direct-API references. The eval suite runs
each problem in **Lane A** (a direct OpenMDAO/OAS/OCP/pyc script) and **Lane B**
(the omd plan pipeline) and asserts parity
(`packages/omd/tests/test_eval_multilane.py`); **Lane C** is the fully-scripted
coverage lane. Committed Lane B plans live under `packages/omd/examples/*/lane_b/`,
and reference-grade reproductions (e.g. Brelje 2018a Fig 5 — 133 cases, every
converged cell identical to the published CSV) are the study-layer validation. This
parity harness is what lets the paper claim the declarative layer reproduces
hand-written MDAO rather than approximating it.
