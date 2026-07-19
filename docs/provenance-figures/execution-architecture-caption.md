# Recommended caption — `execution-architecture.pdf`

**Short (list of figures):**
The `omd` execution / composition architecture.

**Full (in-text):**
**The `omd` execution architecture.** A coding agent drives the `omd` surface
(MCP server or `omd-cli`) to assemble a declarative **`plan.yaml`** — components,
operating point, optional slots, design variables, and objective. The runner
(`run.py`) loads and validates the plan, then **materializes** it into a single
OpenMDAO `Problem`: a **factory + slot registry** resolves each component type to
a builder and dispatches to the **leaf analysis tools** — OpenAeroStruct,
OpenConcept, pyCycle, and the native `evt` model — whose subsystems are composed
into one model. The key composition mechanism is the **slot**: a single component
may fill its drag/propulsion/weight slots with more than one tool (e.g. an
OpenConcept mission with an OpenAeroStruct VLM drag slot), so multi-tool studies
are one materialized problem rather than a hand-wired coupling. Running the driver
produces the recorded outputs — the OpenMDAO recorder `.sql`, the `analysis.db`
PROV-Agent provenance store (the subject of the other figures), the N2 diagram,
and the plots.

This is a system architecture diagram (dataflow/component notation), not a PROV
or UML data model — it is the "how it runs" companion to the "what gets recorded"
provenance figures.
