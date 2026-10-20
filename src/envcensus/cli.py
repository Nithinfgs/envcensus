from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .scan import analyze, load_config, scan


def render_text(report: dict) -> str:
    out = [f"{report['total_reads']} variables read in code, "
           f"{report['total_documented']} documented in .env.example"]
    if report["undocumented"]:
        out.append("\nUNDOCUMENTED (read by code, absent from .env.example/README):")
        for var, locs in report["undocumented"].items():
            f, n = locs[0]
            more = f" (+{len(locs) - 1} more)" if len(locs) > 1 else ""
            out.append(f"  {var}  {f}:{n}{more}")
    if report["unused"]:
        out.append("\nUNUSED (documented, but no code reads it):")
        for var, files in report["unused"].items():
            out.append(f"  {var}  in {', '.join(files)}")
    if report["not_in_ci"]:
        out.append("\nNOT SET IN CI (documented and read, but no workflow sets it):")
        for var in report["not_in_ci"]:
            out.append(f"  {var}")
    if not (report["undocumented"] or report["unused"]):
        out.append("\nNo drift found.")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="envcensus", description=__doc__ or
        "Compare env vars read by code with those documented.")
    ap.add_argument("path", nargs="?", default=".", help="project root (default: .)")
    ap.add_argument("--config", help="path to envcensus.json")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--fail-on", choices=["undocumented", "unused", "any", "none"],
                    default="undocumented", help="exit 1 on this kind of drift (default: undocumented)")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args(argv)

    root = Path(args.path)
    if not root.is_dir():
        print(f"envcensus: not a directory: {root}", file=sys.stderr)
        return 2
    try:
        cfg = load_config(root, args.config)
    except ValueError as exc:
        print(f"envcensus: {exc}", file=sys.stderr)
        return 2

    report = analyze(scan(root, cfg), cfg)
    print(json.dumps(report, indent=2) if args.json else render_text(report))

    bad_undoc, bad_unused = bool(report["undocumented"]), bool(report["unused"])
    fail = {"undocumented": bad_undoc, "unused": bad_unused,
            "any": bad_undoc or bad_unused, "none": False}[args.fail_on]
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
