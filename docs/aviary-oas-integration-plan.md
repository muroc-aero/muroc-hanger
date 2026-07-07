# Plan: OAS inside Aviary — coupled aerostructural wing mass in hangar-avy and omd

Status: **planned** (Phase 0 spike verified 2026-07-07; no implementation yet)

Goal: run OpenAeroStruct *inside* an Aviary sizing loop through the hangar
stack — a physics-based wingbox wing mass replacing Aviary's empirical FLOPS
wing weight — exposed two ways:

1. **Native avy** — OAS as an Aviary *external subsystem*, everything inside
   `.venv-avy`, driven by the `hangar.avy` tools/CLI.
2. **Multitool omd** — an omd plan that couples the tools at the omd level:
   either the native path wrapped in `avy/Sizing` (tight coupling in the
   subprocess), or the existing main-venv `oas/Aerostruct` factory feeding a
   wing-mass override into `avy/Sizing` (loose coupling across the venv
   boundary).

This is the first *nested* tool composition in the hangar: today's omd plans
place tools side by side in one OpenMDAO model; here one tool runs inside
another tool's optimization loop.

## What upstream already provides

Aviary ships exactly this integration as its flagship external-subsystem
example: `aviary/models/external_subsystems/open_aero_struct/`.

- `OAS_wing_mass_analysis.py` — `OAStructures`, an `om.ExplicitComponent`
  whose `compute()` builds a *nested* OAS wingbox problem (AerostructGeometry
  + 2 AerostructPoints: cruise + 2.5g maneuver at M0.64/SL) and runs an
  internal SLSQP sub-optimization (fuelburn objective; skin/spar thickness,
  twist, t/c, maneuver alpha DVs; strength + fuel-volume constraints).
  Outputs the optimized `wing_mass` (and `fuel_burned`). The wing mesh is
  hard-coded to the advanced-single-aisle planform (`user_mesh()`), which
  upstream itself flags as a limitation.
- `OAS_wing_mass_builder.py` — `OASWingMassBuilder(av.SubsystemBuilder)`,
  a *pre-mission* builder: promotes `fuel` from
  `Aircraft.Fuel.WING_FUEL_MASS_CAPACITY` and `wing_mass` **onto
  `Aircraft.Wing.MASS`**, overriding the FLOPS wing weight for the whole
  sizing problem.
- `run_OAS_wing_mass_example.py` — full mission run: advanced single aisle
  FLOPS deck, 3-phase fixed-profile mission (mach/altitude_optimize False,
  1800 nmi, no takeoff/landing) — i.e. already shaped like our
  SLSQP-tractable missions. Sets ~15 OAS inputs (wingbox airfoil coords,
  thickness/twist CPs, cruise condition, engine mass/location) via
  `prob.set_val()` **after `prob.setup()`** — this is the one part that
  doesn't flow through `run_aviary()`.
- Tests: `test_OAS_wing_mass_analysis.py` (component alone, one nested
  sub-opt) and `test_OAS_wing_mass_builder.py` (builder contract via
  `av.TestSubsystemBuilder`, cheap).

Plumbing facts that shape the plan:

- `run_aviary(aircraft_data, phase_info, subsystems=[...])` already threads
  builders into `prob.load_external_subsystems()` — our runner's one-shot
  entry point needs only a new pass-through argument.
- There is **no post-setup hook** in `run_aviary()`: anything the upstream
  example sets with `set_val()` after `setup()` must instead be baked into
  the builder (`set_input_defaults` on the pre-mission group) for our
  config-dict-driven tools. That's the main piece of hangar-side code.
- `load_external_subsystems` merges subsystem metadata into the problem —
  no extra metadata registration needed for the wing-mass case.

## Phase 0 — feasibility spike (DONE, verified)

All verified on 2026-07-07 against the pinned uptreams (Aviary v1.0.1,
OAS v2.12.0):

- OAS v2.12.0 declares `numpy>=1.21` (no upper cap) and
  `openmdao>=3.35,!=3.40` → installs cleanly into `.venv-avy`
  (numpy 2.4.6, OpenMDAO 3.44.0) together with `ambiance` (the atmosphere
  dependency the component imports):
  `VIRTUAL_ENV=$PWD/.venv-avy uv pip install -e upstream/OpenAeroStruct ambiance`.
- The upstream component test passes in `.venv-avy`
  (`test_OAS_wing_mass_analysis.py`, 1 passed in ~45 s — that is one full
  nested wingbox sub-optimization under numpy 2).
- `OASWingMassBuilder` imports and instantiates in `.venv-avy`
  (`av.SubsystemBuilder` is public API).

So the numpy-2 venv split does **not** block this: the OAS pin is
numpy-2-clean even though the *main* venv holds it at numpy<2 for
openconcept's sake. OAS simply gets installed a second time, into
`.venv-avy`.

Runtime envelope (drives everything below): one nested sub-opt ≈ 45 s, and
the pre-mission component re-runs every outer optimizer iteration →
a full coupled sizing is plausibly **15–45 min with SLSQP**. Upstream's own
example says "use the most performant optimizer installed" (prefers
SNOPT/IPOPT). Treat wall-clock as the top risk, not convergence.

## Architecture A — native avy: OAS as an Aviary external subsystem

Everything runs inside `.venv-avy`; the tool surface stays JSON-config.

### A1. Venv + pins

- Add `openaerostruct` (editable `upstream/OpenAeroStruct` at the existing
  `OAS_REF`) + `ambiance` to `scripts/setup-avy-venv.sh`.
- Add the same to `packages/avy/Dockerfile` (build ARG `OAS_REF` mirrors the
  existing `AVY_REF` pattern).
- No change to root `pyproject.toml` — the main venv is untouched.

### A2. Hangar-side builder (the real code)

`packages/avy/src/hangar/avy/subsystems/oas_wing_mass.py`:

- `build_oas_wing_mass(config: dict) -> SubsystemBuilder` — wraps upstream's
  `OAStructures` in our own thin builder (do NOT fork the 567-line component;
  import it from `aviary.models.external_subsystems.open_aero_struct`).
- Converts a JSON config dict into `set_input_defaults()` calls on the
  pre-mission group — replacing the example's post-setup `set_val()` block.
  Config keys: wingbox airfoil coords (default: the example's arrays),
  `twist_cp`, `spar_thickness_cp`, `skin_thickness_cp`, `t_over_c_cp`,
  `fuel_lbm`, `fuel_reserve_lbm`, `CD0`, `cruise_mach`, `cruise_altitude_m`,
  `cruise_range_nmi`, `cruise_SFC_1_per_s`, `engine_mass_lbm`,
  `engine_location_m`.
- Validates config keys strictly with difflib suggestions (same contract as
  `_merge_options` in `missions.py`).
- Registry: `EXTERNAL_SUBSYSTEMS = {"oas_wing_mass": ...}` with a
  description + config schema for discoverability, mirroring
  `MISSION_TEMPLATES`.
- Lazy imports throughout (`require_aviary()` pattern): in the main venv the
  module imports, listing works, and building raises the standard
  install-instruction error. New `require_openaerostruct()` alongside
  `require_aviary()` with `setup-avy-venv.sh` instructions.
- Known limitation carried from upstream, documented in the registry entry
  and reference.md: the wing mesh is hard-coded to the advanced-single-aisle
  planform — this subsystem is only physically meaningful on that deck until
  upstream generalizes `user_mesh()` to read `Aircraft.Wing.*`. The tools
  should *warn* (ValidationFinding, warning severity) when the deck is not
  `advanced_single_aisle` / `bench_FwFm`.

### A3. Runner + tools

- `runner.py`: `_solve_sizing(..., subsystems=())` → forwarded to
  `run_aviary(..., subsystems=list(subsystems))`. Same for
  `run_off_design_problem` / `run_payload_range_problem` (they re-run the
  sizing internally and take the same path).
- New tool `add_external_subsystem(name, subsystem, config=None)`
  (in `tools/aircraft.py`): validates against the registry + config schema,
  stores `(subsystem_name, config)` on the `AvySession` aircraft entry
  (same accumulate-then-run pattern as `define_aircraft` overrides). A
  `list_external_subsystems` tool surfaces the registry.
- `run_sizing`/`run_off_design`/`run_payload_range`: materialize builders
  from the stored (name, config) pairs in `_prepare_run` and pass them down.
- Results: `extract_sizing_results` gains `design.wing_mass_lbm`
  (`Aircraft.Wing.MASS`) so the override is observable; add a
  `subsystem.wing_mass_applied` ValidationFinding (info) recording
  FLOPS-vs-OAS wing mass delta.
- New optional `run_sizing` kwarg `max_iter` already exists; expose the
  nested sub-opt's `maxiter` via builder config (`sub_opt_max_iter`,
  default upstream's) to keep runaway runs bounded.
- CLI + avy-cli-guide skill: new `add-external-subsystem` command page,
  workflows.md gets a coupled-sizing walkthrough with honest runtime
  numbers.

### A4. Native parity example (three lanes)

`packages/avy/examples/single_aisle_oas_wing/` following the established
layout:

- **Lane A** (oracle): adaptation of upstream's
  `run_OAS_wing_mass_example.py` — same deck, same fixed-profile 1800 nmi
  phase_info, SLSQP, `verbosity=0`, print `key: value` results. Golden
  anchors on `gross_mass_lbm`, `total_fuel_mass_lbm`, **`wing_mass_lbm`**
  (the quantity this example exists for), `range_nmi`.
- **Lane B**: avy-cli script JSON — `load_aircraft_template` →
  `add_external_subsystem oas_wing_mass` → `configure_mission` (a new
  `oas_wing_example` entry in `MISSION_TEMPLATES` pointing at a
  `hangar.avy.config.missions_oas_wing` module that reproduces the
  example's phase_info) → `run_sizing`.
- **Lane C**: scripted MCP tool-surface test + blind-agent prompt
  ("size the single aisle with a physics-based OAS wing mass and report how
  far it moves the wing mass vs the empirical estimate").
- Parity: A↔B at `rel=1e-6` (same code path, same venv); golden at
  `rel=2e-3`. A second cheap contract test asserts the FLOPS-only baseline
  wing mass differs from the OAS-coupled one (the integration is actually
  doing something).
- **Gate before writing goldens**: run Lane A once; if SLSQP does not
  converge (upstream prefers IPOPT/SNOPT), fall back per the established
  playbook — pin the profile harder / relax target range — and document a
  negative result honestly if no SLSQP-tractable variant exists. Mark all
  of it `slow`; CI keeps running only the aviary-free contract tests, the
  full lanes run via `.venv-avy` locally (same status as the existing avy
  parity suites).

## Architecture B — multitool omd

Two distinct flavors; build B1 first (it reuses everything from A), keep B2
as the follow-on that actually exercises cross-venv coupling.

### B1. Tight coupling: external subsystem through `avy/Sizing` (small)

The OAS-in-Aviary problem is just another Aviary run, so it flows through
the existing subprocess factory nearly for free:

- `avy_worker.py`: accept `spec["external_subsystems"] =
  [{"name": ..., "config": {...}}]`, materialize via the A2 registry
  (the worker already runs in `.venv-avy` where OAS now lives), pass to
  `run_aviary(subsystems=...)`. Also emit `wing_mass_lbm` in the results
  JSON.
- `factories/avy.py`: pass-through config key `external_subsystems`
  (validated shape only — name resolution happens in the worker, which is
  where the registry is importable); add `wing_mass_lbm` to `output_names`.
- omd example `packages/omd/examples/avy_oas_wing/`: plan.yaml =
  the A4 case as a one-component omd plan; Lane A subprocess-runs A4's
  Lane A script (exact pattern of `avy_single_aisle`); Lane C scripted
  builder-tools test. Goldens shared from A4's `shared.py`.
- Fast aviary-free unit tests in `packages/omd/tests/test_avy_factory.py`:
  config pass-through, `wing_mass_lbm` advertised, bad subsystem name
  rejected by the worker (exercised only in slow lanes).

### B2. Loose coupling: `oas/Aerostruct` → `avy/Sizing` override (the
multitool headline)

Main-venv OAS wingbox computes the wing mass; omd feeds it into the Aviary
subprocess as a deck override. One-way coupling (no feedback), which omd's
sequential composition already models:

- New `avy/Sizing` capability: **override inputs**. Config key
  `override_inputs: {wing_mass_lbm: "aircraft:wing:mass"}` declares
  OpenMDAO inputs on the component; at `compute()` each is written into
  `spec["overrides"]` (converting to the deck variable's units). This
  generalizes the existing `target_range_nm`-only input mechanism.
- Units seam (must be explicit, not implicit): OAS `structural_mass` is kg
  and is the *structure only*; Aviary `aircraft:wing:mass` is lbm and
  carries `wing_weight_ratio` semantics. The plan-level connection needs a
  small `units/Convert` passthrough component (kg→lbm, factor config) —
  omd shared vars connect same-units paths only. Check whether
  `wing_weight_ratio≈1.25` style dressing is wanted or whether raw wingbox
  mass is the study's point; surface that as a plan `decision`.
- Example plan: `oas/Aerostruct` (wingbox, single-aisle-like planform
  matching the A4 mesh) → convert → `avy/Sizing` (advanced single aisle,
  fixed-profile mission). DV sweep potential: `t_over_c_cp` or span at the
  OAS end, gross mass at the Aviary end — a real two-tool trade study and
  the natural `run_study` demo.
- Parity oracle problem: there is no single upstream script that does this
  loose coupling, so Lane A is *compositional*: run OAS raw (existing OAS
  Lane A infrastructure) → hand its wing mass to the avy Lane A script as a
  deck override. The lanes then check the hangar plumbing end to end, and
  the B1/A4 tight-coupled result provides the physical cross-check
  (loose-coupled result should land near the tight-coupled one when fed the
  same wingbox mass — document the expected gap: tight coupling re-optimizes
  the wing per outer iteration, loose coupling freezes it).

## Sequencing and estimates

| Step | Contents | Size |
|---|---|---|
| 1 | A1 venv/pins + A2 builder & registry + unit tests | ~1 day |
| 2 | A3 runner/tools/CLI/results/validation | ~1 day |
| 3 | A4 native parity lanes + goldens (gated on SLSQP run) | ~0.5–1 day, dominated by run time |
| 4 | B1 worker/factory pass-through + omd example | ~0.5 day |
| 5 | B2 override inputs + convert component + coupled plan/study | ~1–1.5 days |
| 6 | Docs: aviary-server-plan.md addendum, CLAUDE.md, skills sync | ~0.5 day |

Risks, ranked:

1. **Wall-clock**: nested sub-opt (~45 s) × outer iterations. Mitigations:
   fixed-profile mission (already), `sub_opt_max_iter` config, coarse
   `num_box_cp` option, everything marked `slow`, goldens run locally.
2. **SLSQP convergence of the coupled problem**: upstream example prefers
   SNOPT/IPOPT. Gate goldens on an actual converged SLSQP run (step 3
   before step 4/5 goldens); IPOPT-only fallback is a documented negative
   result, and the example still ships Lane B/C contract tests.
3. **Hard-coded mesh**: the subsystem is single-aisle-specific until
   upstream generalizes `user_mesh()`. Scope all examples to that deck;
   warn on others. Generalizing the mesh from `Aircraft.Wing.*` is
   explicitly out of scope (it's an upstream contribution, not a wrapper).
4. **Upstream API drift**: `aviary.models.external_subsystems...` is an
   example namespace, not core API — pin-protected (AVY_REF), but note it
   in the reference so a pin bump re-checks the import path.
