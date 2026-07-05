# Recommended caption — `plan-dag-ontology.pdf`

*(The file keeps its historical name; the figure is now a UML class diagram,
not a PROV/DAG view — see the note below.)*

**Short (list of figures):**
The analysis-plan data model (UML class diagram).

**Full caption:**

> **The analysis-plan data model.** A UML class diagram (equivalently, a DoDAF
> DIV-2 logical data model) of the declarative plan that `omd` materializes into
> an OpenMDAO problem. The plan is the composite class; each schema section is a
> class with a multiplicity (filled diamond = composition). The two genuine
> embedded graphs appear as reflexive associations — `Component —connections→
> Component` and `Phase —depends_on→ Phase` — and the `traces_to` links
> (design variables, constraints, and the objective → requirements) tie intent
> to design. Header tint groups the sections (model, optimization, intent,
> process) and carries no formal meaning. Every class and field is taken from
> `plan_schema.py`.
>
> *Why UML and not PROV:* the plan is a structured document — a data model,
> not a process or a provenance record. Its lineage (the plan is a single PROV
> entity, versioned and derived by `replan`/`execute` activities) is shown in
> the Layer 2 figure (`omd-provagent`); this figure is the plan's anatomy.
