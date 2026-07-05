# Figure → code map (review guide)

Each ontology figure encodes a schema that lives in the codebase. This guide
maps **every element in each figure to the exact code that defines it**, so a
reviewer can check the diagram against ground truth without reverse-engineering
it. Line numbers are anchors as of the last sync — if a `grep` for the named
symbol lands elsewhere, trust the symbol name over the number and update this
file.

Each `.tex` also names its own sources in a header comment; this file is the
consolidated, element-by-element version. `check_layout.py` covers geometry
(no node/label overlaps); this file covers *semantic* correctness (are the
classes, edges, and vocabulary right).

**How to review one figure:** open the figure PDF and the source file(s) in the
right column side by side, and walk the rows top to bottom. A figure is correct
when (a) every box/class in the figure appears in the code, (b) every code
concept the figure claims to be complete about (the vocabulary legends) is fully
listed, and (c) every edge matches a relation the code actually emits.

Quick regeneration + geometry check:

```bash
cd docs/provenance-figures
for f in prov-metamodel session-graph omd-provagent plan-dag; do
  tectonic -X compile -o . "$f-ontology.tex"
done
python3 check_layout.py            # geometry only; this file is the semantics
```

---

## 1. `prov-metamodel-ontology.tex` — abstract W3C PROV / PROV-Agent

The only figure **not** tied to a hangar schema: it is the standard W3C PROV
data model that the other two PROV figures instantiate. Review it against the
**W3C PROV-DM spec** and the PROV-Agent paper, not against code.

| Figure element | Ground truth | Verify |
|---|---|---|
| Entity (yellow ellipse), Activity (blue rect), Agent (orange pentagon) | W3C PROV-DM three core types | Shapes + the conventional class colours match the notation reused by figs 2–3 |
| `used`, `wasGeneratedBy`, `wasDerivedFrom`, `wasInformedBy` | PROV-DM core relations | Arrow directions: activity→entity (`used`), entity→activity (`wasGeneratedBy`), entity→entity (`wasDerivedFrom`), activity→activity (`wasInformedBy`) |
| `wasAssociatedWith` (activity→agent), `wasAttributedTo` (entity→agent), drawn dashed | PROV-Agent associations (arXiv:2508.02866, cited in header) | These are the two agent links the Layer-2 figure reuses as dashed edges |

No hangar source files back this figure — it is the shared vocabulary. If it
changes, figs 2 and 3 must follow.

---

## 2. `session-graph-ontology.tex` — Layer 1, the `@capture_tool` session graph

**Primary source:** `packages/sdk/src/hangar/sdk/provenance/db.py`
(5-table SQLite schema + read-time edge inference).

### Nodes ↔ tables

| Figure node | Table (DDL) | `db.py` anchor | Verify |
|---|---|---|---|
| `ToolCall` activity (attrs: `call_id, tool_name, inputs_json, outputs_json, status, duration_s, seq`) | `tool_calls` | `db.py:81` (`CREATE TABLE tool_calls`, `seq` at `:84`) | Every attribute in the box is a column; `seq` is the ordering key |
| `Decision` activity (attrs: `decision_type, reasoning, selected_action, prior_call_id, confidence`) | `decisions` | `db.py:96` (`:99` `seq`) | Column names match; `prior_call_id` is the (optional) back-link |
| `Conclusion` (drawn as a Decision with `decision_type='conclusion'`, `metadata_json` per-req verdict) | `decisions` row + auto-verdict | `db.py:441` (latest `metadata_json` row); verdict logic in `provenance/conclusion.py:27` `derive_conclusion` | Conclusion is **not** a separate table — confirm it is a specialised `decisions` row |
| `Requirement` entity (attrs: `path, operator, value_json, label`) | `requirements` | `db.py:124` (`:126` `seq`) | The **only** entity in Layer 1 (activity-centric claim) |
| `Session` = PROV Bundle (dashed enclosure) | `sessions` (FK `session_id`) | `db.py:71` | Bundle is the `session_id` foreign key, not a node |
| `agent` pentagon, **dashed/implicit** | *(no table)* | — | Correctly shown as not stored — the LLM/user is not a first-class row. This is the "lighter than PROV" claim (doc §5) |
| (5th table) `seq_counters` | `seq_counters` | `db.py:136` | Not drawn as a node; it backs the `seq` UPSERT. Legend lists 5 tables — confirm the count: `sessions`, `tool_calls`, `decisions`, `cross_references`, `requirements` (the legend names these five; `seq_counters` is infra) |

> ⚠️ **Reviewer note:** the legend's "Tables" box lists five: `sessions`,
> `tool_calls`, `decisions`, `cross_references`, `requirements`. The DDL
> actually defines **six** `CREATE TABLE`s (adds `seq_counters` at `db.py:136`).
> `seq_counters` is a sequence-allocator, not a provenance table, so its
> omission from the concept legend is intentional — but verify that's still the
> right call if the schema grows.

### Edges ↔ inference

The edge **solid/dashed/dotted** distinction is the figure's core claim:
solid = a stored FK, dashed = inferred from `seq` at read time, dotted = agent
association. Ground truth is `get_session_graph` at **`db.py:487`** (the
docstring at `:494` enumerates the inferred edges).

| Figure edge | Style | Stored or inferred | Anchor |
|---|---|---|---|
| `informs` (ToolCall→Decision) | solid | stored (`prior_call_id`) | `decisions` FK, `db.py:96` |
| `cross_tool` (ToolCall→other-server ToolCall, `variables_json`) | solid | stored | `cross_references` table, `db.py:111` |
| `satisfies / violates` (Conclusion→Requirement) | solid | stored/derived | verdict in `conclusion.py:57–61`; emitted per-req |
| `sequence` (ToolCall→ToolCall) | dashed | inferred from monotonic `seq` | `get_session_graph` docstring `db.py:494–497` |
| `decides` (Decision→next ToolCall) | dashed | inferred from `seq` | same (`decision.seq` immediately precedes next `tool_call.seq`) |
| `wasAssociatedWith` (agent→ToolCall) | dotted | implicit (not stored) | no FK — matches the "agent not stored" claim |

**Sequence allocation** (why `seq` is trustworthy for inference): `_next_seq`
at `db.py:457`, single-statement UPSERT `ON CONFLICT … RETURNING` at
`db.py:470–480`. The legend's "inferred at read from monotonic `seq` (UPSERT)"
line refers to exactly this.

Agent-authored node types (`tool_call`, `decision`) come from
`sdk/provenance/tools.py`; the auto-verdict from `sdk/provenance/conclusion.py`.

---

## 3. `omd-provagent-ontology.tex` — Layer 2, the `omd` PROV-Agent instance

**Primary source (vocabulary):**
`packages/results-reader/src/hangar/results_reader/db.py`.
**Primary source (edges emitted per run):** `packages/omd/src/hangar/omd/run.py`.

This figure is a **concrete instance** (one plan run), so review is two-part:
(a) every legend token is a member of the frozen vocabulary sets, and (b) every
drawn edge is a relation `run.py` actually emits.

### (a) Vocabulary legend ↔ frozen sets — must be exhaustive

The legend claims to list `KNOWN_ENTITY_TYPES` and `KNOWN_PROV_RELATIONS` in
full. Diff the legend against the sets:

- **`KNOWN_ENTITY_TYPES`** — `results_reader/db.py:46`. Members: `plan`,
  `run_record`, `assessment`, `surface_def`, `operating_point`, `solver_config`,
  `opt_setup`, `decision`, `aero_results`, `struct_results`, `convergence_info`,
  `model_structure`, `phase`, `acceptance_criterion`, `requirement`,
  `plan_element`, `conclusion`, `study`. → **18 types.** The legend's
  `entity_type` line must list all 18 (it groups them across two rows plus the
  `activity_type` / `agent` split).
- **`KNOWN_PROV_RELATIONS`** — `results_reader/db.py:73`. Members:
  `wasGeneratedBy`, `used`, `wasDerivedFrom`, `wasAssociatedWith`,
  `wasAttributedTo`, `wasInformedBy`, `justifies`, `has_criterion`, `verifies`,
  `satisfies`, `violates`, `precedes`, `has_check`, `executes`, `partOf`. →
  **15 relations.** Legend splits them into PROV-core / domain / agent — confirm
  every member appears in exactly one group.
- **DDL** (the `entities` / `activities` / `prov_edges` tables the instance
  populates): `_DDL` at `results_reader/db.py:98` (`entities` `:99`,
  `activities` `:111`, `prov_edges` `:120`).

> ⚠️ **Reviewer note — `conclusion` vs the figure:** `conclusion` is a
> `KNOWN_ENTITY_TYPE` (Layer 2) that the *drawn instance* does not render as its
> own ellipse — Layer 2 shows `assessment`→`satisfies/violates`→`requirement`
> directly. The conclusion entity + its `satisfies/violates` edges are emitted
> in `run.py:1530–1611`. This is fine (the legend lists it; the instance is one
> illustrative run), but confirm the figure still *claims* completeness only in
> the legend, not in the drawn subgraph.

### (b) Drawn edges ↔ `run.py` emission sites

Every solid edge in the figure should correspond to an `add_prov_edge(...)` call:

| Figure edge (subject→object) | Relation | `run.py` anchor |
|---|---|---|
| `replan` → `plan v(N-1)` | `used` | `run.py:404` |
| `plan v(N)` → `replan` | `wasGeneratedBy` | `run.py:405` |
| `plan v(N)` → `plan v(N-1)` (lineage) | `wasDerivedFrom` | `run.py:394` |
| sub-entities (`surface_def`/`operating_point`/`solver_config`/`opt_setup`) → `plan` | `wasDerivedFrom` | `run.py:243` (loop over sub-elements) |
| `execute` → `plan v(N)` | `used` | `run.py:418` |
| `run_record` → `execute` | `wasGeneratedBy` | `run.py:626` (also `:1643`) |
| `execute` → `prior run_record` (warm-start, dashed entity) | `used (warm-start)` | **illustrative** — no `add_prov_edge` for warm-start exists in `run.py`; the dashed entity + label depict the caching/warm-start concept, not a stored edge. Flag if the figure is meant to be edge-exact |
| result entities (`aero_results`/`mission_results`/`struct_results`/`model_structure`) → `run_record` | (`wasDerivedFrom` in the figure) | **containment, not an explicit edge** — recorded with `parent_id=run_id` (`run.py:1367`, `:1381`, `:1390`, `:538`); no `add_prov_edge("wasDerivedFrom", …)` is emitted for results (contrast the plan sub-entities at `:243`). The derivation is implied by `parent_id` |
| `assess` → `run_record` | `used` | `run.py:1361` |
| `assessment` → `assess` | `wasGeneratedBy` | `run.py:1362` |
| `assessment`→`requirement` | `verifies` → `satisfies`/`violates` | conclusion verdict `run.py:1568`, edges `run.py:1606` (`wasDerivedFrom`) + `:1611` (`satisfies`/`violates`) |
| `requirement` → `acceptance_criterion` | `has_criterion` | present in emission set (`KNOWN_PROV_RELATIONS`) |
| `run_record` → `study` | `partOf` | **emitted by the study runner, not `run.py`** — `study_runner.py:166` (study entity), `:172` (`partOf` edge) |
| agent edges (`coding agent`, `omd` pentagons), dashed, now labeled | `wasAssociatedWith` (activity→agent) / `wasAttributedTo` (entity→agent) | `agent=` values set in `run.py` (`omd` at `:412`; the `coding agent` node is the literal `agent="have-agent"` at `:401`, `created_by="have-agent"` at `:380`) |

> ⚠️ **Reviewer note — `coding agent` label vs the `have-agent` literal:** the
> pentagon reads **coding agent** for readability and to match the other figures,
> but the value actually recorded in the DB is the string `have-agent`
> (`run.py:380`, `:401`) — likewise in the vocabulary legend. The `omd` pentagon
> is the literal runtime agent (`agent="omd"`). If the code later renames
> `have-agent`, update the node label to match (it is a presentational alias
> today).

**Cytoscape rendering / version diff** (how these edges are drawn in the live
DAG viewer, for cross-checking direction conventions): `omd/provenance.py` —
`build_provenance_elements` at `:176` (note it *reverses* PROV edge direction
for top-down layout and treats `partOf` as containment; the static figure keeps
PROV-natural direction, so don't be alarmed by the flip).

---

## 4. `plan-dag-ontology.tex` — the analysis-plan data model (UML class diagram)

**Primary source:** `packages/omd/src/hangar/omd/plan_schema.py` — the
`PLAN_SCHEMA` JSON Schema. **Every class and every field in the figure is a
property in this schema.** Secondary: `materializer.py` (plan → OpenMDAO) and
`plan_graph.py` (the two embedded graphs).

This is the highest-fidelity mapping: each UML class = one top-level schema
property; each attribute compartment = that property's sub-fields. Walk the
schema and the figure together.

### Classes ↔ schema properties

| UML class (tint) | Schema property | `plan_schema.py` anchor | Verify fields shown |
|---|---|---|---|
| **Plan** (composite, slate) | root `metadata` + `composition_policy` | `metadata` `:57`, `composition_policy` `:335` | `id · name · version · parent_version · content_hash · composition_policy` |
| **Component** (blue) | `components[]` | `:262` | `type «factory» · id · source · config.slots` |
| **OperatingPoints** (blue) | `operating_points` | `:162` | `single \| multipoint · flight_points[] · α·M·Re·v·h` |
| **SharedVar** (blue) | `shared_vars[]` | `:308` (`consumers` `:326`) | `name · value · units · consumers[] · rationale` |
| **Solver** (amber) | `solvers[]` | `:343` | `target «scope» · nonlinear{type,opts} · linear{type,opts}` |
| **Constraint** (amber) | `constraints[]` | `:406` (`traces_to` `:420`) | `name · upper · lower · equals · scaler · point` |
| **Optimizer** (amber) | `optimizer` | `:441` | `type · options` |
| **DesignVariable** (amber) | `design_variables[]` | `:353` (`traces_to` `:373`) | `name · lower · upper · units · scaler · ref · initial` |
| **Objective** (amber) | `objective` | `:427` (`traces_to` `:435`) | `name · scaler · units` |
| **Requirement** (rose) | `requirements[]` | `:75` | `id · text · type · priority · status · verification{method,assertion}` |
| **AcceptanceCriterion** (rose) | `requirements[].acceptance_criteria[]` | `:113` | nested under Requirement (hence the composition edge Req→Crit) |
| **Decision** (rose) | `decisions[]` | `:454` | `stage · agent · reason · rationale · references[] · alternatives_considered[]` |
| **AnalysisPlan** (gray) | `analysis_plan` | `:491` | `strategy · replan_triggers[]` |
| **Phase** (gray) | `analysis_plan.phases[]` | `:496` (`depends_on` `:506`) | `id · mode · success_criteria[] · checks[]` |

### Relationships ↔ schema structure

| Figure relationship | Meaning | Ground truth |
|---|---|---|
| Composition diamonds Plan→each section, with multiplicity `1..*`/`0..*`/`0..1` | Plan owns each section | array vs object vs required in `PLAN_SCHEMA`. **Verify multiplicities:** `components` is `required` + array → `1..*`; `operating_points` object → `0..1`; `optimizer`/`objective`/`analysis_plan` single objects → `0..1`; the rest arrays → `0..*`. Root `required` list (`plan_schema.py` top) is the authority for which are mandatory |
| Req → AcceptanceCriterion (nested composition) | criteria live inside a requirement | `acceptance_criteria` nested at `:113` |
| AnalysisPlan → Phase (composition) | phases live inside analysis_plan | `phases` nested at `:496` |
| **Component —connections→ Component** (reflexive assoc) | the component connection graph | `connections[]` schema `:296`; graph built in `plan_graph.py:239` (`build_plan_graph`, component loop) |
| **Phase —depends_on→ Phase** (reflexive assoc) | the phase-dependency DAG | `depends_on` schema `:506`; DAG built in `plan_graph.py:527–530` |
| SharedVar —consumers→ Component | shared vars consumed by components | `consumers` `:326` |
| **traces_to** (DesignVariable/Constraint/Objective → Requirement), dashed | intent traceability | `traces_to` on DV `:373`, Constraint `:420`, Objective `:435` (figure draws two representative arcs — dv→req, obj→crit — and the legend notes constraints trace too) |

> ⚠️ **Reviewer note — completeness of `traces_to`:** the figure draws only
> **two** trace arcs to keep it legible (DesignVariable→Requirement,
> Objective→AcceptanceCriterion) and states in the legend that *design_variables
> · constraints · objective* all carry `traces_to`. Confirm the legend text
> still names all three sources, since Constraint's arc is not drawn.

> ⚠️ **Reviewer note — header tint:** the four tints (model/optimization/intent/
> process) are a *reader grouping only* and carry **no formal UML meaning** —
> they don't correspond to a schema construct. The legend says so; keep it that
> way (don't let a reviewer read them as packages/stereotypes).

---

## Sync checklist

Update the paired figure + this file + `check_layout.py` whenever any of these
change:

| If this changes… | Update |
|---|---|
| `sdk/provenance/db.py` (tables, columns, `get_session_graph` inference) | fig 2 (`session-graph`) + §2 above |
| `results_reader/db.py` `KNOWN_ENTITY_TYPES` / `KNOWN_PROV_RELATIONS` / `_DDL` | fig 3 (`omd-provagent`) legend + §3(a) |
| `omd/run.py` `add_prov_edge(...)` sites | fig 3 edges + §3(b) |
| `omd/plan_schema.py` `PLAN_SCHEMA` (any property/field) | fig 4 (`plan-dag`) + §4 |
| `omd/plan_graph.py` (connection/phase graph construction) | fig 4 reflexive associations |
| node coordinates in any `.tex` | `check_layout.py` (geometry) |

The figures encode the schemas **verbatim** — treat a mismatch found during
review as a bug in the figure (or in this map), not a stylistic choice.
