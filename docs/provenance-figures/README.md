# Provenance ontology figures

Standalone LaTeX/TikZ diagrams of the provenance data models described in
[`../provenance-and-capture-tool.md`](../provenance-and-capture-tool.md). Each
`.tex` is self-contained and compiles to a tightly-cropped PDF (via the
`standalone` document class) suitable for `\includegraphics` in the paper. The
compiled `.pdf`s are committed alongside the sources.

| File | Models | Doc section |
|---|---|---|
| `prov-metamodel-ontology.tex` | The abstract **W3C PROV / PROV-Agent meta-model** — the three classes (entity/activity/agent) and six core relations that the other figures instantiate. | §3 |
| `session-graph-ontology.tex` | **Layer 1** — the `@capture_tool` session graph (SDK). A temporal call/decision trace shared by every leaf server (OAS, OpenConcept, pyCycle, evt). Shows the five SQLite tables as concepts and the stored-vs-inferred edge distinction. | §2 |
| `omd-provagent-ontology.tex` | **Layer 2** — the `omd` PROV-Agent artifact model, as the concrete instance emitted by one plan run, with the full `entity_type` / `relation` vocabulary. | §3 |
| `plan-dag-ontology.tex` | The **analysis-plan data model** — a **UML class diagram** (DoDAF DIV-2 logical data model) of the declarative plan that `omd` materializes and Layer 2 versions. `Plan` is the composite; sections are classes with multiplicities; the component connection graph and phase-dependency DAG are reflexive associations. | plan schema |

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

Every figure exposes a single size knob near the top —
`\newcommand{\figscale}{...}` — that uniformly rescales the whole figure (shapes
*and* text) via TikZ `scale=\figscale, transform shape`. Change the one number
to resize the emitted PDF. The defaults bring each cropped PDF to **~6.4 in
wide**, just inside a single-column text block (`\textwidth` ≈ 6.5 in), so the
four are mutually consistent when dropped into the paper:

| figure | native width | `\figscale` | emitted |
|---|---|---|---|
| `prov-metamodel-ontology` | 6.5 in | `0.70` | 4.6 in |
| `session-graph-ontology`  | 8.4 in | `0.75` | 6.4 in |
| `omd-provagent-ontology`  | 8.7 in | `0.72` | 6.4 in |
| `plan-dag-ontology`       | 9.7 in | `0.65` | 6.4 in |

The knob only sets the *absolute* emitted size; it does not change the
text-to-width ratio, so scaling further down at include time makes the text
smaller. In the paper, prefer sizing at include time with
`\includegraphics[width=\linewidth]{...}` (which guarantees the column fit
regardless of the knob). `plan-dag` and `omd-provagent` are the densest — they
read best given the full text width (or a two-column-spanning `figure*`); the
narrower `session-graph` and `prov-metamodel` are comfortable at
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

## Requirements

Only packages that ship with a standard TeX Live / MiKTeX:

```
standalone, tikz, xcolor
```

TikZ libraries used: `arrows.meta`, `positioning`, `shapes.geometric`,
`shapes.multipart` (UML class boxes in `plan-dag`), `fit`, `backgrounds`,
`calc`.

## Building

```bash
# One figure -> cropped PDF
pdflatex prov-metamodel-ontology.tex
# or
latexmk -pdf prov-metamodel-ontology.tex

# All four
for f in prov-metamodel session-graph omd-provagent plan-dag; do
  pdflatex -interaction=nonstopmode "$f-ontology.tex"
done
```

No local TeX install? Compile in a container, or with `tectonic`:

```bash
tectonic -X compile prov-metamodel-ontology.tex
# or
docker run --rm -v "$PWD":/w -w /w texlive/texlive:latest \
  bash -c 'for f in *-ontology.tex; do pdflatex -interaction=nonstopmode "$f"; done'
```

## Keeping them in sync with the code

These diagrams encode the schemas verbatim. If any of the following change,
update the corresponding figure (each header comment lists the exact files):

- `packages/sdk/src/hangar/sdk/provenance/db.py` — session-graph tables/edges.
- `packages/results-reader/src/hangar/results_reader/db.py` — `KNOWN_ENTITY_TYPES`,
  `KNOWN_PROV_RELATIONS`, and the `entities`/`activities`/`prov_edges` DDL.
- `packages/omd/src/hangar/omd/plan_schema.py` — the plan sections.

For an element-by-element mapping — every box, edge, and legend token tied to
the exact `file:line` that defines it, with a "what to verify" column — see
[`FIGURE-CODE-MAP.md`](FIGURE-CODE-MAP.md). That is the review guide: use it to
check each figure against ground truth (`check_layout.py` covers geometry; the
map covers semantics). Its final table is the change → what-to-update
checklist.
