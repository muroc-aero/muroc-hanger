# Recommended caption — `session-graph-ontology.pdf`

**Short (list of figures):**
Layer 1 — the `@capture_tool` session-graph ontology, in W3C PROV notation.

**Full caption:**

> **Layer 1 — the `@capture_tool` session-graph ontology.** An
> activity-centric call/decision trace, shared by every leaf server (OAS,
> OpenConcept, pyCycle, evt) and stored in five SQLite tables. Drawn in W3C
> PROV notation but deliberately lighter than full PROV: tool calls,
> decisions and conclusions are *activities* (blue rectangles), the
> `requirement` is the only *entity* (yellow ellipse), and the session is a
> PROV **Bundle** (dashed enclosure). The agent is drawn implicit (dashed
> orange pentagon) because the LLM is not recorded as a first-class agent.
> Edge labels keep the schema's own names; solid edges are stored, dashed
> edges are inferred at read time from the monotonic `seq` order, and the
> legend maps each to its notional PROV relation.
