#!/usr/bin/env python3
"""Layout checker for the provenance ontology TikZ figures.

The TikZ figures place nodes at explicit coordinates (in cm) with explicit
minimum sizes (in mm). This script mirrors those placements as geometric
boxes/ellipses and reports the *clear gap* between every pair of nodes, so we
can prove no node overlaps another and that labels have room to breathe.

It is a design/verification aid, not a full TikZ renderer: it models node
bounding boxes and explicitly-placed edge labels. Curved-edge label collisions
still get a final visual check (compile -> PNG), but node-vs-node and
node-vs-label overlaps are caught here numerically.

Usage:
    python3 check_layout.py            # check every figure
    python3 check_layout.py plan-dag   # check one figure by key

Coordinates and sizes below are kept in sync with the .tex files by hand; the
whole point is that this file records the spacing budget each figure was
designed against.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

# Clear-gap threshold (mm). Pairs closer than this are flagged as "tight".
MIN_GAP_MM = 3.0
CM = 10.0  # mm per cm (TikZ default unit is cm)


@dataclass
class Box:
    name: str
    x: float  # center, cm
    y: float  # center, cm
    w: float  # mm
    h: float  # mm
    shape: str = "rect"  # rect | ellipse | pentagon | label

    def half_extent(self, dx: float, dy: float) -> tuple[float, float]:
        """Half-width/height (mm) of the shape's footprint in direction (dx,dy).

        For rects we use the full half-extents; ellipses/pentagons are
        approximated conservatively by their bounding box (slightly pessimistic,
        which is the safe direction for a *minimum* clearance check).
        """
        return self.w / 2.0, self.h / 2.0


@dataclass
class Figure:
    key: str
    title: str
    nodes: list[Box] = field(default_factory=list)


def gap_mm(a: Box, b: Box) -> float:
    """Clear gap (mm) between two axis-aligned bounding boxes.

    Negative => the boxes overlap (by that many mm along the deepest axis).
    """
    ax, ay = a.x * CM, a.y * CM
    bx, by = b.x * CM, b.y * CM
    ahw, ahh = a.w / 2.0, a.h / 2.0
    bhw, bhh = b.w / 2.0, b.h / 2.0
    dx = abs(ax - bx) - (ahw + bhw)  # >0 => separated on x
    dy = abs(ay - by) - (ahh + bhh)  # >0 => separated on y
    if dx >= 0 and dy >= 0:
        return (dx * dx + dy * dy) ** 0.5  # corner-to-corner clearance
    if dx >= 0:
        return dx
    if dy >= 0:
        return dy
    # overlapping on both axes: report the shallower penetration as negative
    return max(dx, dy)


def check(fig: Figure) -> int:
    overlaps: list[tuple[str, str, float]] = []
    tight: list[tuple[str, str, float]] = []
    n = fig.nodes
    for i in range(len(n)):
        for j in range(i + 1, len(n)):
            g = gap_mm(n[i], n[j])
            if g < 0:
                overlaps.append((n[i].name, n[j].name, g))
            elif g < MIN_GAP_MM:
                tight.append((n[i].name, n[j].name, g))
    print(f"\n=== {fig.key}: {fig.title} ===")
    print(f"  {len(n)} nodes/labels, {len(n)*(len(n)-1)//2} pairs")
    if overlaps:
        print(f"  OVERLAPS ({len(overlaps)}):")
        for a, b, g in sorted(overlaps, key=lambda t: t[2]):
            print(f"    ✗ {a:<22} × {b:<22} {g:6.1f} mm")
    if tight:
        print(f"  tight (<{MIN_GAP_MM:.0f} mm, {len(tight)}):")
        for a, b, g in sorted(tight, key=lambda t: t[2]):
            print(f"    · {a:<22} ~ {b:<22} {g:6.1f} mm")
    if not overlaps and not tight:
        print("  ✓ clean — all pairs separated by the margin")
    return len(overlaps)


# =====================================================================
#  Figure specs — kept in sync with the .tex files by hand.
#  x,y in cm (node CENTER); w,h in mm (node minimum size incl. a small
#  inner-sep allowance). Edge labels that sit in open space are modeled as
#  small 'label' boxes so they are checked for clearance too.
# =====================================================================

FIGURES: dict[str, Figure] = {}


def _register(fig: Figure) -> None:
    FIGURES[fig.key] = fig


# ---- prov-metamodel --------------------------------------------------
_register(Figure("prov-metamodel", "W3C PROV / PROV-Agent meta-model", [
    Box("Entity", 0.0, 0.0, 28, 13, "ellipse"),
    Box("Activity", 6.0, 0.0, 28, 13, "rect"),
    Box("Agent", 3.0, 3.4, 24, 16, "pentagon"),
    # edge labels in open space
    Box("used", 3.0, 0.35, 12, 5, "label"),
    Box("wasGeneratedBy", 3.0, -1.65, 26, 5, "label"),
    Box("wasDerivedFrom", -2.7, 0.0, 26, 5, "label"),
    Box("wasInformedBy", 8.7, 0.0, 24, 5, "label"),
    Box("wasAssociatedWith", 5.2, 2.0, 30, 5, "label"),
    Box("wasAttributedTo", 0.8, 2.0, 26, 5, "label"),
]))


# ---- session-graph (Layer 1) ----------------------------------------
# Nodes now in W3C-PROV notation: activities (rect), requirement (entity
# ellipse), agent (implicit pentagon); Session is a Bundle drawn as a fit-box
# enclosure around the trace (not a separate node here).
_register(Figure("session-graph", "Layer 1 — @capture_tool session graph", [
    Box("agent", 12.7, 4.8, 18, 18, "pentagon"),
    Box("t1_ToolCall", 1.0, 2.4, 37, 21),
    Box("d1_Decision", 6.5, 2.4, 37, 21),
    Box("t2_ToolCall", 12.0, 2.4, 37, 21),
    Box("t3_crosstool", 12.0, -1.2, 40, 14),
    Box("Requirement", 1.3, -1.4, 44, 20, "ellipse"),
    Box("Conclusion", 7.2, -1.3, 46, 18),
    Box("lshape", -1.3, -4.9, 74, 30),
    Box("ledge", 6.8, -4.9, 82, 30),
    Box("tables", 14.0, -4.9, 62, 30),
    # edge labels in open space (white-filled, must fit the node gap)
    Box("informs", 3.75, 2.4, 15, 5, "label"),
    Box("decides", 9.25, 2.4, 15, 5, "label"),
    Box("sequence", 6.5, 0.55, 18, 5, "label"),
    Box("cross_tool", 12.0, 0.7, 22, 6, "label"),
    Box("verdict", 4.2, -1.4, 12, 9, "label"),
]))


# ---- omd-provagent (Layer 2) ----------------------------------------
_register(Figure("omd-provagent", "Layer 2 — omd PROV-Agent instance", [
    # agents
    Box("have_agent", 2.5, 7.4, 22, 20, "pentagon"),
    Box("omd", 13.0, 7.5, 22, 20, "pentagon"),
    # plan lineage
    Box("planA", 1.5, 4.8, 30, 15, "ellipse"),
    Box("replan", 6.0, 4.8, 26, 12),
    Box("planB", 10.5, 4.8, 32, 16, "ellipse"),
    # plan sub-entities (fan from planB)
    Box("surface_def", 15.5, 6.2, 26, 9, "ellipse"),
    Box("operating_point", 15.5, 5.0, 32, 9, "ellipse"),
    Box("solver_config", 15.5, 3.8, 28, 9, "ellipse"),
    Box("opt_setup", 15.5, 2.6, 24, 9, "ellipse"),
    # execution
    Box("warm", 5.5, 2.4, 28, 10, "ellipse"),
    Box("execute", 10.5, 2.4, 26, 12),
    Box("run_record", 10.5, -0.1, 30, 13, "ellipse"),
    # results (fan from run_record)
    Box("aero_results", 15.5, 1.1, 28, 9, "ellipse"),
    Box("struct_results", 15.5, -0.1, 30, 9, "ellipse"),
    Box("convergence_info", 15.5, -1.3, 32, 9, "ellipse"),
    Box("model_structure", 15.5, -2.5, 32, 9, "ellipse"),
    # assessment / verification
    Box("assess", 6.0, -1.1, 26, 12),
    Box("assessment", 6.0, -3.4, 28, 11, "ellipse"),
    Box("requirement", 1.5, -3.4, 26, 10, "ellipse"),
    Box("accept_crit", 1.5, -5.2, 32, 11, "ellipse"),
    Box("study", 10.5, -3.0, 22, 10, "ellipse"),
    # legend boxes
    Box("voc_entity", 2.0, -7.7, 124, 28),
    Box("voc_rel", 13.5, -7.7, 88, 28),
    # floating edge labels (two-line where the relation name is long)
    Box("lin_used", 3.85, 4.8, 11, 5, "label"),
    Box("lin_wdf", 8.1, 4.8, 15, 9, "label"),
    Box("sub_wdf", 13.0, 5.5, 15, 9, "label"),
    Box("exec_used", 10.5, 3.5, 11, 5, "label"),
    Box("run_wgb", 10.5, 1.15, 15, 9, "label"),
    Box("warm_used", 8.05, 2.4, 17, 9, "label"),
    Box("res_wdf", 13.0, -0.1, 15, 9, "label"),
    Box("assess_used", 8.1, -0.6, 11, 5, "label"),
    Box("assmt_wgb", 6.0, -2.25, 15, 9, "label"),
    Box("satviol", 3.7, -3.4, 16, 9, "label"),
    Box("has_crit", 1.5, -4.35, 22, 5, "label"),
    Box("partof", 10.5, -1.6, 14, 5, "label"),
]))


# ---- plan-dag (UML class diagram / logical data model) --------------
# Each UML class is one box (name + attribute compartments). Sizes are the
# rendered footprints (approx). The optimization classes share one
# composition tree; the trunk sits in the clear corridor at x=8.2.
_register(Figure("plan-dag", "The analysis-plan data model (UML class diagram)", [
    Box("Plan", 6.6, 8.6, 50, 22),
    # model / topology
    Box("Component", -1.0, 5.8, 30, 20),
    Box("OperatingPoints", 2.8, 5.8, 28, 22),
    Box("SharedVar", 0.9, 3.3, 32, 20),
    # optimization problem (left sub-column)
    Box("Solver", 6.0, 6.4, 32, 20),
    Box("Constraint", 6.0, 4.2, 34, 20),
    Box("Optimizer", 6.0, 2.0, 24, 16),
    # optimization problem (right sub-column, nearest requirements)
    Box("DesignVariable", 10.4, 5.2, 34, 20),
    Box("Objective", 10.4, 2.9, 26, 16),
    # requirements / intent
    Box("Requirement", 14.6, 5.8, 44, 20),
    Box("AcceptanceCriterion", 14.6, 3.4, 40, 20),
    Box("Decision", 14.6, 1.0, 42, 24),
    # analysis process
    Box("AnalysisPlan", 6.6, -0.9, 32, 16),
    Box("Phase", 6.6, -3.1, 40, 24),
    # legend
    Box("legend", 3.0, -6.2, 148, 28),
]))


def main() -> int:
    keys = sys.argv[1:] or list(FIGURES)
    bad = 0
    for k in keys:
        if k not in FIGURES:
            print(f"unknown figure '{k}'; known: {', '.join(FIGURES)}")
            return 2
        bad += check(FIGURES[k])
    print()
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
