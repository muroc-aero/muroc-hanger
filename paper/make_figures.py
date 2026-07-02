#!/usr/bin/env python
"""Collect (and optionally regenerate) the paper's reproduction figures.

Sources:
  brelje  -- packages/omd/demos/brelje_2018a: paper-vs-reproduced Figs 5 & 6
             (--regenerate re-renders from the committed grid CSVs; the full
             sweep itself is run_paper_grid.sh, ~5-9 h, see paper/README.md)
  adler   -- packages/omd/demos/adler_2022a: comparison figs 7, 9-13
             (NOT collected by default: the match against the paper has not
             been verified; the pipeline lives on the adler-2022a-demo branch)
  abu     -- packages/evt/examples/abu_scitech_2026: eVTOL case-study figures
             (NOT collected by default: figures pending verification --
             the numeric grid match is checked by compare_to_golden.py)

Only brelje is collected by default; opt into the unverified sources with
--only adler / --only abu / --all.

Usage (from the repo root):

    uv run python paper/make_figures.py                # Brelje only
    uv run python paper/make_figures.py --regenerate   # re-render Brelje from CSVs
    uv run python paper/make_figures.py --only adler   # unverified, explicit opt-in
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PAPER_DIR = Path(__file__).resolve().parent
REPO_ROOT = PAPER_DIR.parent
FIGURES_DIR = PAPER_DIR / "figures"

BRELJE = REPO_ROOT / "packages/omd/demos/brelje_2018a"
ADLER = REPO_ROOT / "packages/omd/demos/adler_2022a"
ABU = REPO_ROOT / "packages/evt/examples/abu_scitech_2026"


def _copy(src: Path, dest_dir: Path) -> bool:
    if not src.exists():
        print(f"  MISSING {src.relative_to(REPO_ROOT)}")
        return False
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / src.name)
    print(f"  {src.relative_to(REPO_ROOT)} -> "
          f"{(dest_dir / src.name).relative_to(REPO_ROOT)}")
    return True


def _run(cmd: list[str]) -> None:
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def collect_brelje(regenerate: bool) -> bool:
    print("Brelje 2018a (Figs 5 & 6):")
    if regenerate:
        for fig in ("5", "6"):
            grid = BRELJE / "results" / f"fig{fig}_grid.csv"
            if not grid.exists():
                print(f"  MISSING {grid.relative_to(REPO_ROOT)} -- "
                      "run run_paper_grid.sh first")
                return False
            for style in ("contour", "paper"):
                # plotting.py needs pandas, which omd core deliberately
                # excludes -- pull it in for this subprocess only.
                _run(["uv", "run", "--with", "pandas", "python",
                      str(BRELJE / "pipeline/plotting.py"),
                      "--figure", fig, "--style", style])
            _run([sys.executable, str(BRELJE / "pipeline/compare.py"),
                  "--figure", fig])
    dest = FIGURES_DIR / "brelje_2018a"
    ok = True
    for name in ("comparison_fig5.png", "comparison_fig6.png"):
        ok &= _copy(BRELJE / "figures" / name, dest)
    for name in ("fig5_paper.png", "fig6_paper.png"):
        ok &= _copy(BRELJE / "figures" / "reproduced" / name, dest)
    return ok


def collect_adler() -> bool:
    print("Adler 2022a (comparison figs, as committed):")
    dest = FIGURES_DIR / "adler_2022a"
    ok = True
    for src in sorted((ADLER / "figures").glob("comparison_fig*.png")):
        ok &= _copy(src, dest)
    return ok


def collect_abu() -> bool:
    print("AIAA SciTech 2026 eVTOL case study:")
    dest = FIGURES_DIR / "abu_scitech_2026"
    ok = True
    for src in sorted((ABU / "figures" / "reproduced").glob("*.png")):
        ok &= _copy(src, dest)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", choices=["brelje", "adler", "abu"],
                        default=None,
                        help="Collect a single source (adler/abu are "
                             "unverified and only collected explicitly)")
    parser.add_argument("--all", action="store_true",
                        help="Collect every source, including unverified "
                             "adler/abu figures")
    parser.add_argument("--regenerate", action="store_true",
                        help="Re-render Brelje figures from the grid CSVs "
                             "before copying (fast; no re-sweep)")
    args = parser.parse_args()

    sources = [args.only] if args.only else (
        ["brelje", "adler", "abu"] if args.all else ["brelje"])

    ok = True
    if "brelje" in sources:
        ok &= collect_brelje(args.regenerate)
    if "adler" in sources:
        ok &= collect_adler()
    if "abu" in sources:
        ok &= collect_abu()

    print(f"\nFigures collected under {FIGURES_DIR.relative_to(REPO_ROOT)}/"
          + ("" if ok else "  (some sources missing, see above)"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
