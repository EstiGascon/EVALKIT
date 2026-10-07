"""Orchestrator for the Baltic 24 h precipitation misplacement case study.

Steps:
  1. load STVL tp24 gauges for the reported valid window;
  2. compare the three models at the reported initialisation (event maps);
  3. sweep each model across initialisation lead times (predictability maps);
  4. summarise northward displacement / bias / RMSE vs lead time.
"""

from __future__ import annotations

import argparse
import datetime as dt

import pandas as pd
import precip_forecasts as F
import precip_obs as O
import precip_plots as P
import precip_stats as S
from precip_config import MODELS, MODELS_IEKM, PrecipConfig

REPORTED_BASE = dt.datetime(2026, 8, 20, 12)  # the run RTE flagged
# Longitude corridor + threshold used for the "how far north" metric.
LON_MIN, LON_MAX = 21.0, 30.0
CM_THRESHOLD = 5.0  # mm


def main(test: bool = False, models=MODELS, suffix: str = "") -> None:
    """Run the event, fixed-lead and predictability comparisons."""
    cfg = PrecipConfig()
    order = tuple(spec.key for spec in models)

    O.retrieve_observations(cfg)
    obs = O.load_observations(cfg)
    obs_lat = S.obs_mass_weighted_lat(obs, CM_THRESHOLD, LON_MIN, LON_MAX)
    print(f"Gauge rain-mass mean latitude: {obs_lat:.2f} °N")

    if test:
        spec = models[0]
        fld = F.tp24_field(cfg, spec, REPORTED_BASE)
        if fld is not None:
            print(S.score_summary(fld, obs))
        return

    # --- 1. Event intercomparison at the reported base time -----------------
    print("\nEvent forecasts (reported window):")
    event = F.load_event_forecasts(cfg, REPORTED_BASE, models=models)
    P.plot_event_intercomparison(
        cfg, obs, event, f"precip_event_intercomparison{suffix}.png", order=order
    )

    # --- 1b. Same comparison but with every model matched to a fixed lead ---
    # T+54 = lead to the end of the 24 h window (init 21 Aug 00Z, +30-54 h acc).
    print("\nFixed-lead forecasts (T+54 to window end, matched across all models):")
    fixed_lead = F.load_fixed_lead_forecasts(cfg, 54, models=models)
    P.plot_event_intercomparison(
        cfg,
        obs,
        fixed_lead,
        f"precip_event_intercomparison_54h{suffix}.png",
        subtitle="all models matched at T+54 (lead to end of the 24 h window)",
        order=order,
    )

    # --- 2. Predictability sweep + skill summary ----------------------------
    rows: list[dict] = []
    fields_by_model: dict[str, list] = {}
    for spec in models:
        print(f"\nPredictability sweep: {spec.label}")
        fields = F.load_predictability(cfg, spec)
        if not fields:
            continue
        fields_by_model[spec.key] = fields
        P.plot_predictability_grid(
            cfg, obs, fields, f"precip_predictability_{spec.key}.png", spec.label
        )
        for fld in fields:
            row = S.score_summary(fld, obs)
            row["cm_lat"] = S.mass_weighted_lat(
                fld.lats, fld.lons, fld.tp24, CM_THRESHOLD, LON_MIN, LON_MAX
            )
            rows.append(row)

    P.plot_lead_time_comparison(
        cfg,
        obs,
        fields_by_model,
        f"precip_lead_time_comparison{suffix}.png",
        order=order,
    )

    summary = pd.DataFrame(rows)
    summary.to_csv(cfg.results_dir / f"precip_skill_by_lead{suffix}.csv", index=False)
    P.plot_displacement_summary(
        cfg, summary, obs_lat, f"precip_displacement_summary{suffix}.png"
    )
    print(f"\n\u2713 Wrote {len(summary)} forecast scores and figures.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="single-model smoke test")
    ap.add_argument(
        "--variant",
        choices=["hybrid", "iekm"],
        default="hybrid",
        help="third model to compare alongside IFS-control/AIFS-single",
    )
    args = ap.parse_args()
    if args.variant == "iekm":
        main(test=args.test, models=MODELS_IEKM, suffix="_iekm")
    else:
        main(test=args.test, models=MODELS, suffix="")
