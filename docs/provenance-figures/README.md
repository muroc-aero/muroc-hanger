# Architecture & provenance figures

LaTeX/TikZ diagrams of the Hangar execution architecture and the provenance data
models described in
[`../provenance-and-capture-tool.md`](../provenance-and-capture-tool.md).

**Format.** Each figure `.tex` is a bare **`figure*` float** meant to be
`\input` into a paper — it carries only `\begin{figure*} … \end{figure*}` with a
`\caption` and `\label`, no document preamble. The shared TikZ libraries, colour
palette, and in-node text macros live once in [`_preamble.tex`](_preamble.tex);
add it to your paper preamble (after `\usepackage{tikz,xcolor}`). To build/preview
the figures on their own — and to regenerate the committed `.pdf`s — use
[`_preview.tex`](_preview.tex) (see **Building**). The compiled `.pdf`s are
committed alongside the sources as reference renders.

| File | Models | Doc section |
|---|---|---|
| `execution-architecture.tex` | The **omd execution / composition architecture** (a *system* diagram, not a data model) — how a declarative plan is materialized into one OpenMDAO problem that composes the leaf analysis tools through a factory/slot registry, then run and recorded. | §1 |
| `prov-metamodel-ontology.tex` | The abstract **W3C PROV / PROV-Agent meta-model** — the three classes (entity/activity/agent) and six core relations that the other figures instantiate. | §3 |
| `session-graph-ontology.tex` | **Layer 1** — the `@capture_tool` session graph (SDK). A temporal call/decision trace shared by every leaf server (OAS, OpenConcept, pyCycle, evt). Shows the five SQLite tables as concepts and the stored-vs-inferred edge distinction. | §2 |
| `omd-provagent-ontology.tex` | **Layer 2** — the `omd` PROV-Agent artifact model, as the concrete instance emitted by one plan run, with the full `entity_type` / `relation` vocabulary. | §3 |
| `plan-dag-ontology.tex` | The **analysis-plan data model** — a **UML class diagram** (DoDAF DIV-2 logical data model) of the declarative plan that `omd` materializes and Layer 2 versions. `Plan` is the composite; sections are classes with multiplicities; the component connection graph and phase-dependency DAG are reflexive associations. | plan schema |
| `ocp-oas-plan-listing.tex` | A **syntax-highlighted YAML listing** (a `figure`, not a diagram) of the concrete multi-tool plan `ocp_vlm_drag_slot_v1.yaml` — an OpenConcept mission whose drag slot is filled by an OpenAeroStruct VLM wing. The worked example behind `execution-architecture`. | §1 |

The plan-model figure is deliberately **not** a PROV diagram. The plan is a
structured document — a *data model*, not a process or a provenance record — so
it is drawn in UML (the standard formalism for a logical data model). Its
lineage as a single PROV entity (versioned/derived by `replan`/`execute`) is the
Layer 2 figure's job. The file keeps its historical `plan-dag` name.

## Notation

The **three PROV figures** (`prov-metamodel`, `session-graph`, `omd-provagent`)
share the **W3C PROV visual grammar** — *entity* = ellipse, *activity* =
rectangle, *agent* = pentagon — so shape carries the PROV class meaning
consistently. Colour follows the **conventional PROV class palette** (muted for
print): **entity = soft yellow**, **activity = soft blue**, **agent = soft
orange**; edges are monochrome, distinguished by line style (solid / dashed /
dotted). There is no figure-specific accent colour.

The fourth figure, **`plan-dag`, is a UML class diagram**, not a PROV diagram —
the plan is a data model, not a provenance record (see below).

The fifth figure, **`execution-architecture`, is a system architecture diagram**
(dataflow/component notation), not a data model at all: pentagon = agent,
rounded rectangle = pipeline stage / software (blue) or leaf analysis tool
(green), rectangle = data artifact (yellow), cylinder = datastore. It reuses the
same base palette so it reads as part of the set, adding one soft-green tool
colour. Solid edges are data/control flow; dashed edges are registry dispatch /
factory resolution.

- **`prov-metamodel`** — the abstract W3C PROV / PROV-Agent model.
- **`session-graph`** (Layer 1) — drawn in PROV notation but honest that it is a
  *lighter* model (doc §5): it is **activity-centric** (`tool_call`, `decision`,
  `conclusion` are activities; `requirement` is the only entity), the Session is
  a PROV **Bundle** (dashed enclosure), and the agent is **dashed/implicit** (the
  LLM is not a stored first-class agent). Edge labels keep the schema's own names
  with the notional PROV relation given in the legend (solid = stored,
  dashed = inferred from `seq`, dotted = agent association).
- **`omd-provagent`** (Layer 2) — full PROV; solid edges are PROV relations
  (core + PROV-Agent domain), dashed edges are agent associations.
- **`plan-dag`** — a **UML class diagram** (logical data model). `Plan` is the
  composite; each schema section is a class with a multiplicity (filled
  diamond = composition, using the shared-tree form for the optimization
  parts). The two embedded graphs are **reflexive associations**
  (`Component —connections→ Component`, `Phase —depends_on→ Phase`), and
  `traces_to` (design variables / constraints / objective → requirements) is an
  association. Header tint groups the sections (model / optimization / intent /
  process) with no formal meaning. Uses the `shapes.multipart` TikZ library for
  the class boxes.

The figures carry **no baked-in title, subtitle, or prose annotation box** — only
their shape/edge legends. The recommended paper caption for each figure (title +
the explanatory prose that used to sit on the canvas) is in the matching
`*-caption.md`, e.g. `session-graph-caption.md`. Each `.tex` cites the
source-of-truth files (schema DDL, vocabulary sets, edge-emission sites) in a
header comment.

### Sizing

Each figure sets a single size number in its `tikzpicture` options —
`scale=<n>, transform shape` — that uniformly rescales the whole figure (shapes
*and* text). Change that one literal to resize. Because the figures are now
`figure*` floats, the emitted width matters only for `_preview.tex`; in the paper
the float is drawn at whatever the `tikzpicture` scale gives (or wrap the picture
in a `\resizebox{\linewidth}{!}{…}` to force column fit):

| figure | native width | `scale=` | preview width |
|---|---|---|---|
| `prov-metamodel-ontology` | 6.5 in | `0.70` | 4.6 in |
| `session-graph-ontology`  | 8.4 in | `0.75` | 6.4 in |
| `omd-provagent-ontology`  | 8.7 in | `0.72` | 6.4 in |
| `plan-dag-ontology`       | 9.7 in | `0.65` | 6.4 in |
| `execution-architecture`  | 10.3 in | `0.66` | 6.8 in |

The scale only sets the *absolute* size; it does not change the text-to-width
ratio. `plan-dag`, `omd-provagent`, and `execution-architecture` are the densest
— they read best across the full text width (a two-column-spanning `figure*`);
the narrower `session-graph` and `prov-metamodel` are comfortable at
`width=0.7\textwidth`.

## Layout checking

`check_layout.py` mirrors each figure's node placements (coordinates in cm, sizes
in mm) as geometric boxes and reports the clear gap between every pair of nodes
and edge-labels, so node/label collisions are caught numerically rather than by
eye. It is the design tool the current spacing was tuned against — keep it in
sync when you move nodes.

```bash
python3 check_layout.py            # check every figure
python3 check_layout.py plan-dag   # one figure by key
```

A clean figure reports only sub-3 mm "tight" pairs (white-filled edge labels
sitting in node gaps), never "OVERLAPS". Curved-edge label collisions still get a
final visual check (compile → PNG).

`check_layout.py` models the four ontology/data-model figures (fixed node
coordinates). `execution-architecture` uses relative `fit`/`calc` placement, so
it is verified by compiling `_preview.tex` and eyeballing, not by the checker.

## Requirements

Only packages that ship with a standard TeX Live / MiKTeX:

```
tikz, xcolor          (the diagram figures, via _preamble.tex)
listings              (the plan-YAML listing; loaded by _preamble.tex)
article               (_preview.tex build driver)
```

TikZ libraries used (all declared in `_preamble.tex`): `arrows.meta`,
`positioning`, `shapes.geometric` (cylinder datastores in
`execution-architecture`), `shapes.multipart` (UML class boxes in `plan-dag`),
`fit`, `backgrounds`, `calc`.

## Building

The figure `.tex` files are `figure*` floats — they do **not** compile on their
own (no document class or preamble). Two ways to use them:

**In your paper** — pull in the shared preamble once, then `\input` each float:

```latex
\usepackage{tikz}
\usepackage{xcolor}
\input{docs/provenance-figures/_preamble}   % libraries + palette + macros
...
\input{docs/provenance-figures/execution-architecture}   % \ref{fig:execution-architecture}
```

**Preview / regenerate the committed PDFs** — `_preview.tex` renders every figure
in order, neutralising the float wrapper so nothing floats to the end:

```bash
tectonic -X compile _preview.tex        # -> _preview.pdf (one page per figure)
# or
pdflatex _preview.tex

# no local TeX? use a container:
docker run --rm -v "$PWD":/w -w /w texlive/texlive:latest \
  latexmk -pdf _preview.tex
```

## Keeping them in sync with the code

These diagrams encode the schemas verbatim. If any of the following change,
update the corresponding figure (each header comment lists the exact files):

- `packages/sdk/src/hangar/sdk/provenance/db.py` — session-graph tables/edges.
- `packages/results-reader/src/hangar/results_reader/db.py` — `KNOWN_ENTITY_TYPES`,
  `KNOWN_PROV_RELATIONS`, and the `entities`/`activities`/`prov_edges` DDL.
- `packages/omd/src/hangar/omd/plan_schema.py` — the plan sections.
- `packages/omd/src/hangar/omd/{run,materializer,registry,slots}.py` — the
  `execution-architecture` pipeline, factory/slot registry, and datastores.

For an element-by-element mapping — every box, edge, and legend token tied to
the exact `file:line` that defines it, with a "what to verify" column — see
[`FIGURE-CODE-MAP.md`](FIGURE-CODE-MAP.md). That is the review guide: use it to
check each figure against ground truth (`check_layout.py` covers geometry; the
map covers semantics). Its final table is the change → what-to-update
checklist.
