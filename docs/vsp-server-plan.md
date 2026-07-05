# Plan: hangar-vsp — OpenVSP / VSPAERO MCP server + CLI

Add `packages/vsp/` wrapping [OpenVSP](https://github.com/OpenVSP/OpenVSP)
(parametric aircraft geometry) and its bundled VSPAERO solver (VLM / panel
aerodynamics, stability derivatives), patterned on the existing
`packages/ocp/`, `packages/pyc/`, and `packages/evt/` servers.

Status: **pre-plan / design**. The go/no-go gate is the Phase 0 build spike.

## Why this tool

OpenVSP fills a gap none of the current hangar tools cover:

- **Real parametric full-configuration geometry** — fuselage, nacelles,
  tails, pods, props — vs OAS's single-lifting-surface meshes.
- **Wetted areas, volumes, and mass properties** (CompGeom/DegenGeom) —
  cheap analyses that agents constantly want during conceptual design.
- **VSPAERO**: VLM and thick-panel aero on the full configuration,
  stability-derivative mode, control-surface deflections, actuator disks.
- **Parasite drag buildup** on actual wetted geometry.
- **CAD-grade exports** (STEP/IGES/STL) for downstream tools.

It would become the geometry hub of the toolchain. Two integration points
already exist:

- **OAS upstream already imports OpenVSP.** `generate_vsp_surfaces()` in
  `openaerostruct/geometry/utils.py:392` converts a `.vsp3` model to OAS
  surface dicts via DegenGeom. A "author geometry in VSP → analyze
  aerostructurally in OAS" handoff is nearly free, and it enables a
  VSP-VLM vs OAS-VLM parity example for the paper lanes.
- The code path OAS uses (`vsp.VSPVehicle()`) confirms modern OpenVSP
  supports **multiple independent model instances**, so per-session vehicle
  state in a `SessionManager` works without the legacy global-singleton
  problem.

## Upstream summary

Key facts that shape the wrapper:

- **Distribution**: compiled C++ with SWIG Python bindings. There is **no
  official PyPI wheel** — the Python API ships inside platform release zips
  (built against one specific Python version) or is compiled from source
  with CMake/SWIG. This is the single biggest difference from every current
  upstream (all pip-installable pure Python).
- **API shape**: one `openvsp` module. Geometry is authored through the
  parm API (`AddGeom`, `SetParmVal`, parm IDs); analyses run through the
  Analysis Manager (`SetAnalysisInputDefaults` / `Set*AnalysisInput` /
  `ExecAnalysis`); results come back through the ResultsMgr plus files.
- **VSPAERO sequencing**: `ExecAnalysis("VSPAEROComputeGeometry")` (writes
  the DegenGeom VLM or `.tri` panel representation) MUST precede
  `ExecAnalysis("VSPAEROSinglePoint"/"VSPAEROSweep")`.
- **File-based solver**: VSPAERO is a separate multithreaded executable that
  runs in a working directory and writes `.polar`, `.stab`, `.lod`,
  `.history` files. Each run needs a managed per-run scratch dir (under
  `HANGAR_DATA_DIR`), and the wrapper must parse `.history` for
  wake-iteration convergence.
- **No analytic derivatives.** Unlike OAS, VSPAERO has no adjoint;
  gradient-based optimization through it is finite-difference only
  (expensive, noisy). The omd factory should default it to
  analysis/DOE/sweep roles.
- **Headless**: builds cleanly with `-DVSP_NO_GRAPHICS=true`; no GUI needed
  for API + VSPAERO. Visualization is matplotlib from DegenGeom points, not
  screenshots.
- License: NASA Open Source Agreement (NOSA) v1.3 — fine for wrapping.

## Impact on the-hangar (what actually changes)

Nothing in the SDK, envelope, provenance, or session architecture needs to
change — this addition mostly validates the pattern. The deltas:

1. **`upstream-pins.env` / dev-setup**: current upstreams are
   `git clone && pip install`. OpenVSP needs a `scripts/setup-openvsp.sh`
   that CMake-builds with `-DVSP_NO_GRAPHICS=true` + Python bindings
   (~20–40 min first build), pinned by git SHA like the others.
   (Alternative — downloading the pinned release zip per platform — is
   fragile because the bundled build must match Python 3.11 exactly;
   prefer source builds for reproducibility.)
2. **Docker/CI**: the first multi-stage compiled image. To keep CI sane,
   publish a `hangar-openvsp-base` image (compiled headless OpenVSP +
   VSPAERO binaries + bindings) to a registry that both CI and the package
   Dockerfile `FROM`. This is the one genuinely new infra piece.
3. **Dependency declaration**: `hangar-vsp`'s pyproject cannot depend on
   `openvsp` (not on PyPI). Handle exactly like OAS does — optional import
   with a clear install-instruction error; dev-setup/Docker provide it.
4. **Binary artifacts** (minor): `ArtifactStore` is JSON-oriented; geometry
   exports (`.vsp3`, `.step`, `.adb`) are binary. Store them alongside
   plots under the run's data dir (probably sufficient) or add a small
   file-artifact helper to the SDK if a second tool needs it.

## Phase 0 — build spike (go/no-go gate)

1. Build OpenVSP locally on macOS with Python bindings
   (`-DVSP_NO_GRAPHICS=true`), pick and pin the version/SHA.
2. Script end-to-end without any hangar code: wing geom →
   `VSPAEROComputeGeometry` → `VSPAEROSweep` → parse `.polar`/`.history`.
3. Repeat inside a Linux container to validate the future base image.
4. Exit criteria: clean bindings import on both platforms, sweep results
   match the GUI for the same model, runtimes understood.

## Phase 1 — packaging

- `scripts/setup-openvsp.sh` (clone at pin, cmake build, `pip install` the
  built python packages into `.venv`), wired into `dev-setup.sh`.
- `VSP_REF` in `scripts/upstream-pins.env`.
- `docker/` base-image Dockerfile + registry publish workflow;
  `packages/vsp/Dockerfile` `FROM hangar-openvsp-base`.

## Phase 2 — package skeleton + core tools

`packages/vsp/` mirroring evt/pyc layout (namespace rule: `__init__.py`
only at `src/hangar/vsp/`, never `src/hangar/`): `server.py`, `state.py`
(`VspSession` holding `VSPVehicle` instances + run scratch dirs),
`config/defaults.py`, `tools/`, `cli.py` (`vsp-cli`/`vsp-server`, next free
default port), `viz/`, tests. All server plumbing from
`hangar.sdk.server_main.run_server_main`; provenance four-pack from
`build_provenance_tools`.

Tool surface (~14 tools, deliberately NOT a 1:1 parm-API wrap):

| Group | Tools |
|---|---|
| Geometry | `load_vehicle_template` (wing-only; conventional wing+tail+fuselage; …), `define_geometry` (declarative JSON spec → parm API), `import_vsp3` |
| Analysis | `compute_geometry` (CompGeom/DegenGeom: wetted area, volumes, mass props), `run_vspaero_sweep` (alpha/beta/Mach arrays, `method=vlm\|panel`, ReCref, control-surface deflections, NCPU), `run_stability_derivatives`, `compute_parasite_drag` |
| Cross-tool | `export_geometry` (vsp3/STEP/STL/DegenGeom CSV), `export_oas_surfaces` |
| SDK standard | provenance four-pack, artifacts, `get_run`, `get_detailed_results`, `visualize`, `get_last_logs`, `reset` |

Agents must never touch raw parm IDs — the `define_geometry` spec is the
design-sensitive piece of this phase (model it on evt's `define_vehicle`
strict-key approach: reject unknown keys with typo suggestions).

`ValidationFinding` squawks to encode from day one:

- Inviscid VLM: no CLmax/stall; total drag requires the parasite buildup.
- Wake iterations not converged (parse `.history` residuals).
- Panel method requires watertight geometry; fall back with a finding.
- FD-only derivatives — flag any optimization use.
- Panel-count vs runtime estimate before expensive sweeps.

## Phase 3 — visualization + CLI guide

- `visualize`: planform / 3-view from DegenGeom points (matplotlib,
  oas-cli plot style), drag polar, spanload from `.lod`.
- `vsp-cli-guide` skill in `packages/vsp/skills/` (structure of
  `oas-cli-guide`), synced via `scripts/sync-skills.sh`.

## Phase 4 — cross-tool + omd factory

- `export_oas_surfaces` → `hangar.oas` `create_surface` payloads via
  `generate_vsp_surfaces`.
- omd `vsp_aero` factory (`packages/omd/factories/vsp_aero.py`):
  ExternalCode-style component, FD partials only, documented as
  analysis/sweep-role by default.
- **Parity example** (paper-lane material): same trapezoidal wing in
  VSP-VLM vs OAS-VLM, CLα / induced-drag comparison, three-lane structure
  like the existing example suites.
- Golden tests against OpenVSP's shipped example models.

## Phase 5 — deploy

Per the `new-tool` skill: docker-compose service (+ viewer read-only
mount), Caddyfile routes, `VSP_TRANSPORT`/`VSP_HOST`/`VSP_PORT` env vars,
OIDC via `hangar.sdk.auth`, `DEPLOY.md`, `.mcp.json` entry,
`HANGAR_VIEWER_DBS` update.

## Difficulty estimate

Roughly 1.5–2× evt/pyc effort. The server/CLI/provenance scaffold is
mechanical given the SDK (~50%); the compiled-upstream packaging and base
image is the hard ~30%; the declarative geometry spec design is the
remaining ~20%. Phase 0 de-risks nearly all of it.

## References

- [OpenVSP GitHub](https://github.com/OpenVSP/OpenVSP)
- [Python API packages README](https://github.com/OpenVSP/OpenVSP/blob/main/src/python_api/packages/README.md)
- [OpenVSP Python API docs](https://openvsp.org/pyapi_docs/latest/)
- [OpenVSP API docs](https://openvsp.org/api_docs/latest/)
- VSPAERO API sequencing: [ComputeGeometry before SinglePoint/Sweep](https://groups.google.com/g/openvsp/c/E7AGQJgxy0M),
  [VSPAERO Python scripting](https://groups.google.com/g/openvsp/c/TeBWnp7ZbvQ)
- [pip package proposal thread](https://groups.google.com/g/openvsp/c/5zeWrVJdolo) (no official PyPI wheel as of 2026-07)
