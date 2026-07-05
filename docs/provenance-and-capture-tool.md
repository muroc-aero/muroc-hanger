# Provenance in the Hangar: `@capture_tool`, the session graph, and the PROV-Agent model

**Audience:** new developers getting up to speed on how provenance works across
the Hangar MCP servers, and the authors of the-hangar paper who need a precise,
citable account of the design, its relationship to PROV-Agent
([arXiv:2508.02866](https://arxiv.org/abs/2508.02866)), and where it differs.

**TL;DR.** The Hangar records provenance at **two layers**:

1. A **session-graph layer** shared by the leaf tool servers (OAS, OpenConcept,
   pyCycle, evt). Every MCP tool call is auto-captured by a decorator into a
   SQLite `tool_calls` table; agent reasoning is captured explicitly via a
   `log_decision` tool; cross-tool handoffs via `link_cross_tool_result`. The
   graph is a *temporal call/decision trace*.
2. A **PROV-Agent artifact layer** in `omd` (the plan runner). It uses an
   explicit W3C-PROV-shaped model — versioned **entities**, **activities**, and
   typed **prov_edges** (`used`, `wasGeneratedBy`, `wasDerivedFrom`, …) — to
   record *what artifacts were produced, from what, by which activity, and how
   they satisfy requirements*.

Layer 1 is cheap, automatic, and universal. Layer 2 is richer, declarative, and
reserved for the plan-based composition tool where artifacts (plans, runs,
assessments) genuinely have versions and derivations. Both render to the same
Cytoscape.js viewer.

> **Ontology diagrams.** Standalone, compilable LaTeX/TikZ diagrams of the data
> models discussed below live in [`provenance-figures/`](provenance-figures/).
> The three PROV figures — `prov-metamodel-ontology.tex` (the abstract W3C PROV /
> PROV-Agent base model), `session-graph-ontology.tex` (Layer 1), and
> `omd-provagent-ontology.tex` (Layer 2, one plan run) — share the W3C PROV
> visual grammar with the conventional class colours (entity = soft yellow,
> activity = soft blue, agent = soft orange). The fourth,
> `plan-dag-ontology.tex`, is a **UML class diagram** of the plan data model that
> Layer 2 versions (the plan is a declarative document, not a provenance record).
> Each ships a compiled `.pdf`, is `\includegraphics`-ready, and cites its schema
> source in a header comment. See `provenance-figures/README.md` to build and
> `provenance-figures/FIGURE-CODE-MAP.md` for an element-by-element map from each
> figure to the code that defines it.

---

## 1. Why two layers

PROV-Agent's motivating problem is that "agents can hallucinate or reason
incorrectly, propagating errors when one agent's output becomes another's
input," so it wants to capture agent prompts/responses/decisions *and* tie them
to downstream workflow outcomes. The Hangar shares that goal but splits it by
cost/benefit:

- For a **single leaf analysis server** (run one VLM analysis, read the CL), the
  useful provenance question is "*what sequence of calls happened, with what
  inputs/outputs, and why did the agent choose them?*" A per-call trace answers
  that with zero per-tool boilerplate — hence the decorator (Layer 1).
- For the **`omd` plan runner**, which composes OAS + OpenConcept + pyCycle into
  one declarative plan, the useful question is "*this result artifact — what plan
  version produced it, what did that plan derive from, which requirements does it
  satisfy or violate?*" That needs first-class versioned artifacts and typed
  derivation edges — the PROV-Agent model proper (Layer 2).

---

## 2. Layer 1 — the `@capture_tool` session graph (SDK)

*Ontology diagram: [`provenance-figures/session-graph-ontology.tex`](provenance-figures/session-graph-ontology.tex).*

### 2.1 How the decorator works

`capture_tool` wraps every tool function so a call is recorded with no work
required at the call site.

- Source: `packages/sdk/src/hangar/sdk/provenance/middleware.py:100`
- Applied at registration time, e.g.
  `packages/oas/src/hangar/oas/server.py:228` —
  `mcp.tool()(capture_tool(create_surface))`. Every leaf server wraps every
  analysis/artifact/observability tool the same way.

Per call the wrapper (`middleware.py:104-207`):

1. Mints a `call_id` (uuid4) and resolves the active `session_id`
   (`_get_session_id`, `middleware.py:37`).
2. Serialises `kwargs` to `inputs_json` up front (`_safe_json`,
   `middleware.py:82`; numpy-aware via `hangar.sdk.serialization`).
3. `await`s the wrapped function, timing it with `time.perf_counter()`.
4. **Injects `_provenance` into the returned dict** (`middleware.py:143`):
   `{"call_id", "session_id"}`. This is the hook that lets the agent thread
   causality — it passes that `call_id` back as `prior_call_id` on the next
   `log_decision`.
5. On a typed `HangarError`, converts it to an **error envelope**
   (`make_error_envelope`) instead of raising, so the agent receives an
   actionable `error.code`/`details` (`middleware.py:124-138`).
6. In a `finally`, records the row **off the event loop** via
   `asyncio.to_thread(_record)` (`middleware.py:158-201`) so the SQLite write
   never blocks the async server. Recording failures are swallowed — provenance
   is best-effort and never breaks a tool call.
7. Every `_FLUSH_EVERY = 5` calls it flushes the graph JSON to disk
   (`middleware.py:92`, `flush.py`).

The wrapper preserves the original signature (`wrapper.__signature__`,
`middleware.py:206`) so FastMCP still introspects the real parameters.

### 2.2 Session resolution (multi-tenant correctness)

Session id is resolved with a priority chain (`middleware.py:37-48`):
`ContextVar` (test isolation) → **per-user active session** (set by
`start_session`) → per-process default. The per-user map
(`_user_session_ids`, `middleware.py:27`) is what keeps one user's
`start_session` on a shared HTTP server from repointing another user's
recording. On stdio there is one user per process.

### 2.3 The schema (what a session graph stores)

DDL: `packages/sdk/src/hangar/sdk/provenance/db.py:70-145`. Five tables:

| Table | Row = | Key columns |
|---|---|---|
| `sessions` | one workflow | `session_id`, `user`, `project`, `tool`, `started_at`, `notes` |
| `tool_calls` | one auto-captured call | `call_id`, `seq`, `tool_name`, `inputs_json`, `outputs_json`, `status`, `error_msg`, `started_at`, `duration_s`, `tool` |
| `decisions` | one agent reasoning step | `decision_id`, `seq`, `decision_type`, `reasoning`, `prior_call_id`, `selected_action`, `confidence`, `metadata_json` |
| `cross_references` | one tool→tool handoff | `source_call_id`/`source_tool`, `target_call_id`/`target_tool`, `variables_json`, `notes` |
| `requirements` | one asserted requirement | `path`, `operator`, `value_json`, `label` |

Ordering is a per-session monotonic `seq` claimed atomically by an UPSERT
(`_next_seq`, `db.py:457`) so concurrent threads/processes can't collide.

The three agent-authored tools that populate this layer are built once and bound
to each server's session manager (`build_provenance_tools`,
`packages/sdk/src/hangar/sdk/provenance/tools.py:34`):

- **`start_session`** (`tools.py:37`) — opens or *joins* a session. Joining an
  existing id is how cross-tool workflows share one graph.
- **`log_decision`** (`tools.py:71`) — the agent-reasoning capture. Writes
  `decision_type` (`dv_selection`, `result_interpretation`,
  `convergence_assessment`, …), free-text `reasoning`, `selected_action`,
  `confidence`, and crucially `prior_call_id` linking back to the tool call that
  informed it.
- **`link_cross_tool_result`** (`tools.py:107`) — records a data dependency
  across servers (e.g. OAS `CD` → OpenConcept mission), with the actual
  `variables` passed. This is the multi-agent/multi-tool edge.
- **`export_session_graph`** (`tools.py:155`) — flushes graph JSON and returns
  viewer URLs.

### 2.4 The concluding stage

`record_conclusion` (`packages/sdk/src/hangar/sdk/provenance/conclusion.py:102`)
is a distinct act: the agent picks the run that answers the study, and the
verdict is **auto-derived** — each persisted requirement is re-evaluated against
that run's results with the same comparator the validation block uses
(`derive_conclusion`, `conclusion.py:27`), so the per-requirement verdict cannot
drift from the numbers. It is stored as a `decision` row with
`decision_type='conclusion'` and the payload in `metadata_json`
(read back by `db.get_conclusion`, `db.py:426`).

### 2.5 How the graph is built (edges are inferred, not stored)

The session layer stores nodes (calls, decisions) but **infers edges from `seq`
order** at read time (`get_session_graph`, `db.py:487-640`):

- `tool_call → decision` labelled **informs** when `decision.prior_call_id`
  matches (the explicit causal edge).
- `decision → next tool_call` labelled **decides** when a decision sits between
  two calls.
- `tool_call[n] → tool_call[n+1]` labelled **sequence** otherwise.
- `cross_tool` edges from the `cross_references` table.

`graph_to_elements` (`db.py:643`) normalises this into Cytoscape `{data:{…}}`
elements, sharing the `kind`/`label`/`relation` shape with the omd builder so one
stylesheet renders either graph.

### 2.6 The response envelope (the provenance carrier)

Every analysis tool returns a **versioned envelope** (`make_envelope`,
`packages/sdk/src/hangar/sdk/envelope/response.py:25`): `schema_version`,
`tool_name`, `run_id`, `timestamp`, `inputs_hash` (a sha256 fingerprint,
`response.py:16`), `results`, and optional `validation`/`telemetry`. The
decorator then staples `_provenance.call_id` onto it. The envelope is the
contract that makes provenance composable: `run_id` addresses the artifact,
`inputs_hash` fingerprints reproducibility, `call_id` threads causality.

### 2.7 What Layer 1 does **not** capture

- **No raw LLM prompts/responses/token traces.** The agent's *decisions* are
  captured (as it chooses to log them), but the model transcript is not — the
  server sees tool calls, not the conversation. (Contrast PROV-Agent §2.9.)
- **No artifact versioning or content hashing** at this layer (that's Layer 2).
  `inputs_hash` fingerprints a call's inputs but there is no `wasDerivedFrom`
  chain between successive results.
- **Edges are heuristic** (seq-adjacency) except `informs`/`cross_tool`. A
  decision the agent never logs leaves no edge.
- **Decision capture is voluntary.** If the agent skips `log_decision`, the trace
  still has the calls but not the "why." The MCP server instructions push the
  agent to log, but nothing enforces it.

---

## 3. Layer 2 — the PROV-Agent model in `omd`

*Ontology diagrams:
[`provenance-figures/prov-metamodel-ontology.tex`](provenance-figures/prov-metamodel-ontology.tex)
(the abstract W3C PROV / PROV-Agent base model),
[`provenance-figures/omd-provagent-ontology.tex`](provenance-figures/omd-provagent-ontology.tex)
(the concrete PROV-Agent artifact model for one plan run), and
[`provenance-figures/plan-dag-ontology.tex`](provenance-figures/plan-dag-ontology.tex)
(the plan artifact this layer versions and derives from).*

`omd` implements the PROV-Agent model directly. Its module docstring says so:
`packages/omd/src/hangar/omd/db.py:1-5` ("Implements the PROV-Agent model with
entities, activities, provenance edges, and run case data") and
`packages/omd/src/hangar/omd/provenance.py:1-5`.

### 3.1 Schema

The read-side schema lives in the results-reader package so it can be consumed
without OpenMDAO as a dependency:
`packages/results-reader/src/hangar/results_reader/db.py:98-152`.

- **`entities`** (`db.py:99`) — a versioned artifact. Columns: `entity_id`,
  `entity_type`, `created_at`, `created_by`, `plan_id`, `version`,
  `content_hash` (SHA256), `storage_ref` (path to the YAML/recorder/N2 on disk),
  `user`. Entities also carry a `parent_id`/`metadata` on the write side
  (`record_entity`, `packages/omd/src/hangar/omd/db.py:155`).
- **`activities`** (`db.py:111`) — a process. Columns: `activity_id`,
  `activity_type`, `started_at`, `completed_at`, `agent`, `status`.
- **`prov_edges`** (`db.py:120`) — a typed relation: `relation`, `subject_id`,
  `object_id`, `timestamp`.
- **`run_cases`** / **`run_keys`** (`db.py:128`, `137`) — per-iteration recorder
  data and study-case indexing (adjacent to provenance, not part of the PROV
  triple).

### 3.2 The catalog (the vocabulary)

These are soft-validated sets, so a typo warns rather than corrupts
(`db.py:46-92`):

**Entity types** (`KNOWN_ENTITY_TYPES`, `db.py:46`): `plan`, `run_record`,
`assessment`, `surface_def`, `operating_point`, `solver_config`, `opt_setup`,
`decision`, `aero_results`, `struct_results`, `convergence_info`,
`model_structure`, `phase`, `acceptance_criterion`, `requirement`,
`plan_element`, `conclusion`, `study`.

**Relations** (`KNOWN_PROV_RELATIONS`, `db.py:73`): the PROV-Agent core
`wasGeneratedBy`, `used`, `wasDerivedFrom`, `wasAssociatedWith`,
`wasAttributedTo`, `wasInformedBy`; plus domain relations `justifies`,
`has_criterion`, `verifies`, `satisfies`, `violates`, `precedes`, `has_check`,
`executes`, `partOf`.

### 3.3 What a run records — the execution path

A plan run emits provenance in the following order
(`packages/omd/src/hangar/omd/run.py`; each step names the `record_*` /
`add_prov_edge` call site). Note the distinction between an explicit
`wasDerivedFrom` edge and `parent_id` **containment** (a column the DAG builder
renders separately) — not every parent link is a derivation edge.

1. **Decompose the plan into sub-entities.** Each plan section becomes an
   entity — `surface_def` (`run.py:71`), `operating_point` (`:89`/`:113`),
   `solver_config` (`:135`), `opt_setup` (`:155`), plus per-slot `slot_config`
   (`:226`) — all `created_by="omd"` with `parent_id` = the plan entity. A loop
   then adds an explicit `wasDerivedFrom` edge from each sub-entity to the plan
   (`:242-243`).
2. **Record the plan entity** (`entity_type="plan"`, `created_by="have-agent"`,
   `run.py:377`). On a *replan*, a **replan** activity is recorded
   (`activity_type="replan"`, `agent="have-agent"`, `:398`) with the version
   lineage: `plan vN wasDerivedFrom plan v(N-1)` (`:394`), `replan used` the
   parent plan (`:404`), `plan vN wasGeneratedBy replan` (`:405`). This is how
   plan evolution is tracked.
3. **Record the execute activity** (`activity_type="execute"`, `agent="omd"`,
   `run.py:409`) and the edge `execute used plan` (`:418`).
4. **Materialize and solve** the OpenMDAO problem. On success, record the
   `run_record` entity (`run.py:616`) and the edge `run_record wasGeneratedBy
   execute` (`:626`). (The optimize-mode path mirrors this at
   `:1632`/`:1639`/`:1643`.)
5. **Fan out the result entities** — `aero_results` (`run.py:1367`),
   `mission_results` (`:1381`), `struct_results` (`:1390`), and
   `model_structure` (`:538`) — each recorded with `parent_id` = the run record
   (**containment**; no separate `wasDerivedFrom` edge is emitted for these, so
   the derivation is implied by `parent_id`, not by an explicit edge as in
   step 1).
6. **Assess against requirements** (concluding stage): an **assess** activity
   (`activity_type="assess"`, `run.py:1345`) and an `assessment` entity
   (`:1352`), with `assess used run_record` (`:1361`) and `assessment
   wasGeneratedBy assess` (`:1362`). The auto-derived verdict writes a
   `conclusion` entity that `wasDerivedFrom` the run (`:1606`) and one
   `satisfies` / `violates` edge per requirement (`:1611`).

### 3.4 Distinctive capabilities Layer 2 adds

- **Artifact versioning + content hashing.** Plans are versioned entities with a
  `content_hash`; the viewer computes a **version diff** between `v(N-1)` and
  `vN` (`provenance_diff`, `provenance.py:1069`; `_compute_plan_diff`,
  `provenance.py:1135`). You can see exactly what changed between replans.
- **Requirement verification as first-class edges.** `requirement` /
  `acceptance_criterion` entities with `satisfies`/`violates`/`verifies` edges to
  runs — the plan's intent is in the graph, not just its execution.
- **PROV-correct directionality.** The builder deliberately reverses PROV edges
  for a top-to-bottom visual layout while keeping the stored relation semantics
  (`build_provenance_elements`, `provenance.py:176`; reversal at `:290-301`).
- **Studies.** A `study` entity collects many case `run_record`s via `partOf`
  edges. This is emitted by the study runner, not the single-run path
  (`study_runner.py:166` records the `study` entity, `:172` adds the `partOf`
  edge).

---

## 4. The PROV-Agent approach (arXiv:2508.02866), summarized

PROV-Agent (accepted at IEEE e-Science 2025) contributes a provenance model
purpose-built for **agentic AI workflows**, extending the **W3C PROV** standard:

- **Agents** — LLM-based entities that plan, act, and interact with peer agents.
- **Activities** — agent operations: reasoning, decision-making, tool
  invocations.
- **Entities** — prompts, responses, tool outputs, intermediate results.
- **Relationships** — causality chains showing how one agent's output influences
  downstream actions.

Key properties of the reference system:

- Captures **agent prompts, responses, and decisions** and integrates them with
  the broader workflow context and downstream outcomes.
- Uses the **Model Context Protocol (MCP)** as the agent–tool interaction
  surface and **data-observability** techniques for near-real-time capture.
- An **open-source, near-real-time** implementation spanning edge/cloud/HPC,
  integrated with a workflow/observability substrate (the group's Flowcept
  lineage).
- Goals: **reproducibility** (decision chains across federated environments),
  **debugging** (locating error propagation), **hallucination-risk assessment**,
  and support for **critical queries** about agent reliability.

---

## 5. How the-hangar differs from PROV-Agent

| Dimension | PROV-Agent | the-hangar |
|---|---|---|
| **PROV grounding** | Extends W3C PROV explicitly (agents/activities/entities). | Layer 2 (`omd`) mirrors W3C PROV relations (`used`, `wasGeneratedBy`, `wasDerivedFrom`, `wasAttributedTo`, …). Layer 1 is a lighter call/decision trace, not full PROV. |
| **Capture surface** | Data-observability instrumentation over the agent runtime; captures prompts + responses + decisions. | A **server-side decorator** (`@capture_tool`) over the *tool* boundary. Captures tool inputs/outputs/timing/status automatically; captures agent *decisions* only when the agent calls `log_decision`. **Raw prompts/LLM responses are not stored.** |
| **What "agent" means** | The LLM agent(s) are modelled entities in the graph. | The recorded `agent` is the **tool/runtime** (`omd`, `have-agent`), not the LLM. Agent reasoning enters as `decision` nodes, not as a modelled PROV Agent with a transcript. |
| **Instrumentation cost** | Requires integrating the observability layer into the agent framework. | Zero per-tool boilerplate: one decorator at registration; best-effort, off-event-loop, never breaks a call. Runs on plain stdio/HTTP MCP with no external substrate. |
| **Storage / deployment** | Near-real-time store across edge/cloud/HPC (Flowcept-lineage). | Local **SQLite**, WAL-mode, co-located with artifacts; periodic JSON flush; a self-hosted Cytoscape.js viewer. No external services. |
| **Verification semantics** | General causality/reliability queries. | Domain-specific: **auto-derived requirement verdicts** (`satisfies`/`violates`) that cannot drift from the numbers, plus **plan version diffs** and content hashes. Provenance is tied to *engineering acceptance criteria*, not just lineage. |
| **Multi-tool composition** | Multi-agent causality chains. | Explicit `link_cross_tool_result` edges carrying the actual handed-off variables (e.g. `CD` → mission), and `omd` composing tools into one declarative plan graph. |
| **Reproducibility handle** | Decision-chain replay. | Versioned response **envelope** with `inputs_hash` fingerprint + `run_id` artifact address + exportable standalone script (`omd export`). |

**One-line distinction for the paper.** PROV-Agent instruments the *agent
runtime* to record the LLM's prompts, responses, and decisions as first-class
W3C-PROV agents/entities. the-hangar instruments the *tool boundary*: it
auto-captures every MCP tool call server-side for free, layers optional
agent-decision nodes on top, and — uniquely — binds the resulting artifact
lineage to **auto-derived, drift-proof engineering-requirement verdicts** and
**content-hashed, diffable plan versions**. It trades transcript-level agent
fidelity for near-zero-overhead, deployment-free capture and domain-grounded
verification.

**Honest limitations to state.** (1) No LLM prompt/response capture, so
agent-internal hallucination is only observable through logged decisions and
tool outcomes, not the reasoning trace. (2) Session-layer edges are heuristic
(seq-adjacency) except `informs`/`cross_tool`. (3) Decision logging is voluntary.
(4) Two provenance layers with different schemas is added conceptual surface —
justified by the cost/benefit split (§1) but a real seam a reader should know
about.

---

## 6. Code map — where to look

**Layer 1 (SDK session graph)** — `packages/sdk/src/hangar/sdk/`
- `provenance/middleware.py` — the `@capture_tool` decorator, session resolution.
- `provenance/tools.py` — `start_session`, `log_decision`,
  `link_cross_tool_result`, `export_session_graph`.
- `provenance/db.py` — DDL, `record_*`, `get_session_graph` (edge inference),
  `graph_to_elements`.
- `provenance/conclusion.py` — auto-derived requirement verdicts.
- `provenance/flush.py` — graph JSON persistence.
- `envelope/response.py` — versioned envelope + `inputs_hash`.
- Registration example: `packages/oas/src/hangar/oas/server.py:228` onward.

**Layer 2 (omd PROV-Agent model)** — `packages/omd/src/hangar/omd/`
- `db.py` — write-side `record_entity` / `record_activity` / `add_prov_edge`
  (re-exports the read seam).
- `run.py` — where entities/activities/edges are emitted during a run
  (`used`, `wasGeneratedBy`, `wasDerivedFrom`, `satisfies`/`violates`, `partOf`).
- `provenance.py` — timeline, Cytoscape element builder, DAG HTML viewer,
  version diff.
- Shared read schema + catalog:
  `packages/results-reader/src/hangar/results_reader/db.py` (`_DDL`,
  `KNOWN_ENTITY_TYPES`, `KNOWN_PROV_RELATIONS`, `query_provenance_dag`).

**Try it**
```bash
# Layer 1: run any leaf tool via CLI/MCP, then export the session graph.
#   (each analysis tool result carries _provenance.call_id / run_id)

# Layer 2: run an omd plan and inspect the PROV-Agent DAG
omd-cli run plan.yaml --mode analysis
omd-cli provenance <plan_id> --format text          # human timeline
omd-cli provenance <plan_id> --format html -o dag.html   # Cytoscape DAG
omd-cli viewer                                       # interactive viewer
```
