"""Command-line interface: ``run``, ``plan``, ``template`` and ``models``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from casetool.config import load_config
from casetool.models import PRESETS
from casetool.pipeline import describe, run

TEMPLATE = """\
# Case-study configuration for case_study_tool.
# Run:   python case_study_tool/run_case.py run   this_file.yaml
# Check: python case_study_tool/run_case.py plan  this_file.yaml

name: my_case                 # output folder name: case_study_tool/output/<name>/
title: "My case study"

variable: tp                  # tp (precipitation) | ws10 (10 m wind speed)
window:
  end: "2026-02-05 00"        # end of the accumulation / aggregation window (UTC)
  hours: 24                   # window length; for ws10 instant use 0
  statistic: sum              # tp: sum | ws10: instant, max or mean

leads: [24, 48]               # hours from model run to window end; runs = end - lead

models:                       # presets: ifs, aifs, destine (iekm, fallback i4ql), pilot_dt (j5j2)
  - ifs
  - aifs
  - destine
  # - {preset: destine, expver: j5j2, label: "DestinE j5j2"}     # preset with another expver
  # - label: "My RD experiment"                                  # any MARS experiment
  #   class: rd
  #   expver: abcd
  #   stream: oper            # default oper
  #   type: fc                # default fc
  #   cycles: [0]             # run hours available
  #   step_rules: [[120, 1], [240, 3]]   # steps <= 120 hourly, then 3-hourly to 240

domain:
  extent: [-10.0, 4.5, 35.5, 44.5]      # [W, E, S, N]
  zooms:                                 # optional extra figures for sub-areas
    andalusia: [-7.6, -1.5, 35.8, 38.7]

region:                       # optional: statistics only inside this outline (drawn on maps)
  name: Iberia
  countries: [Spain, Portugal]
  # admin1: {country: Italy, regions: [Toscana]}
  # box: [W, E, S, N]

observations:
  enabled: true
  sources: [synop, hdobs]
  min_coverage: 1.0           # fraction of reports needed (multi-day sums / wind max-mean)

thresholds: [1, 10, 25, 50, 100]   # categorical scores (POD, FAR, FBI, ETS)

plot:
  style: contour              # contour (shaded) | gridbox (native grid cells)
  levels: null                # null = automatic colour scale, or a list of levels
  orography: true             # add a model-orography figure
"""


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python case_study_tool/run_case.py``."""
    parser = argparse.ArgumentParser(
        prog="run_case.py",
        description="Compare forecast models with SYNOP/HDOBS observations for a case study.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="retrieve data, verify and write figures/tables")
    p_run.add_argument("config", type=Path)
    p_run.add_argument("--force", action="store_true", help="ignore cached data")
    p_run.add_argument(
        "--workers", type=int, default=6, help="parallel MARS retrievals"
    )
    p_run.add_argument("--no-obs", action="store_true", help="skip observations")

    p_plan = sub.add_parser(
        "plan", help="show runs, steps and checks without retrieving"
    )
    p_plan.add_argument("config", type=Path)

    p_tpl = sub.add_parser("template", help="print a commented configuration template")
    p_tpl.add_argument("-o", "--output", type=Path, help="write to this file")

    sub.add_parser("models", help="list model presets")

    args = parser.parse_args(argv)
    if args.command == "template":
        if args.output:
            args.output.write_text(TEMPLATE)
            print(f"Wrote {args.output}")
        else:
            print(TEMPLATE)
        return 0
    if args.command == "models":
        for key, m in PRESETS.items():
            print(
                f"{key:<9} {m.label:<16} class={m.mars_class} expver={'|'.join(m.expvers)} "
                f"cycles={list(m.cycles)} steps={list(m.step_rules)}"
            )
        return 0
    cfg = load_config(args.config)
    if args.command == "plan":
        print(describe(cfg))
        return 0
    run(cfg, force=args.force, workers=args.workers, with_obs=not args.no_obs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
