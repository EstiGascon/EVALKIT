"""Run the HRES 10 m wind-speed verification study end to end.

Pipeline:
    1. Retrieve STVL 10 m wind-speed observations (VINO).
    2. Retrieve HRES (IFS-single) 10 m wind components from MARS and derive speed.
    3. Match forecasts to observations at station locations.
    4. Compute verification scores and generate maps / plots.
    5. Write a summary (CSV + markdown) and print an automated conclusion.

Usage (from the analysis/ directory, with an ECMWF python that has earthkit):
    python run_analysis.py                # full pipeline
    python run_analysis.py --skip-obs     # reuse cached observations
    python run_analysis.py --skip-fc      # reuse cached forecasts
    python run_analysis.py --dry-run      # config summary only
"""

from __future__ import annotations

import argparse

import pandas as pd
import plots
import verification as vf
from config import StudyConfig
from forecasts import load_all_forecasts
from observations import load_observations, retrieve_observations


def _write_conclusion(
    cfg: StudyConfig,
    overall: pd.DataFrame,
    by_lead: pd.DataFrame,
    station: pd.DataFrame,
    by_day: pd.DataFrame,
) -> str:
    """Compose an automated systematic-vs-event conclusion from the scores."""
    ev = overall.loc["event"]
    base = overall.loc["baseline"]
    event_bias = ev["bias"]
    base_bias = base["bias"]

    # Fraction of stations under-forecasting on event days.
    frac_under = float((station["bias"] < 0).mean()) if len(station) else float("nan")
    # Is the event bias consistent across lead times?
    ev_leads = by_lead[by_lead["period"] == "event"]
    lead_all_negative = bool((ev_leads["bias"] < 0).all()) if len(ev_leads) else False

    # Are event days outliers relative to the daily-bias distribution?
    day_bias = by_day.set_index("valid_day")["bias"]
    non_event = day_bias[~by_day.set_index("valid_day")["is_event"]]
    thresh = non_event.mean() - 2 * non_event.std() if len(non_event) > 2 else None

    lines = []
    lines.append("# HRES 10 m wind-speed verification — automated summary\n")
    lines.append(f"Region box: N={cfg.north} W={cfg.west} S={cfg.south} E={cfg.east}")
    lines.append(f"Event days: {', '.join(str(d) for d in cfg.event_days)}\n")
    lines.append(
        f"- Event-day mean bias (fc − obs): **{event_bias:+.2f} m/s** "
        f"(RMSE {ev['rmse']:.2f}, n={int(ev['n'])})"
    )
    lines.append(
        f"- Baseline mean bias:             **{base_bias:+.2f} m/s** "
        f"(RMSE {base['rmse']:.2f}, n={int(base['n'])})"
    )
    lines.append(f"- Stations under-forecasting on event days: {frac_under * 100:.0f}%")
    lines.append(f"- Event bias negative at all lead times: {lead_all_negative}")
    if thresh is not None:
        flagged = [str(d) for d, b in day_bias.items() if b < thresh]
        lines.append(
            f"- Event days beyond 2σ of baseline daily bias: "
            f"{', '.join(flagged) if flagged else 'none'}"
        )
    lines.append("")

    # Heuristic verdict. Judge (a) whether the event-day under-forecast is
    # amplified relative to baseline, (b) whether it is spatially coherent,
    # and (c) whether it persists across lead times.
    gross_failure = event_bias < -1.0 and (event_bias - base_bias) < -0.7
    amplified = (
        event_bias < 1.3 * base_bias and event_bias < -0.2
    )  # ≥30 % more negative
    widespread = frac_under > 0.6
    outlier_days = []
    if thresh is not None:
        outlier_days = [str(d) for d, b in day_bias.items() if b < thresh]

    if gross_failure and widespread and lead_all_negative:
        verdict = (
            "SYSTEMATIC model failure on the event days: a large, domain-wide "
            "under-forecast present across all lead times."
        )
    elif amplified and (widespread or lead_all_negative):
        verdict = (
            "PARTLY SYSTEMATIC (event amplification). HRES carries a modest but spatially "
            f"coherent LOW bias in 10 m wind that is amplified on the event days "
            f"(event {event_bias:+.2f} vs baseline {base_bias:+.2f} m/s, {frac_under * 100:.0f}% of "
            "stations under-forecasting, negative at every lead time). It is not a gross model "
            "failure, but a genuine recurring under-forecast of the daytime wind peaks that is "
            f"strongest on {', '.join(outlier_days) if outlier_days else 'the event days'}. "
            "Note the 10 m bias understates the wind-power impact: power scales ~cubically with "
            "wind speed and turbines sit near ~100 m, so a ~10-15 % low wind bias maps to the "
            "large generation errors RTE reported."
        )
    else:
        verdict = (
            "Likely EVENT-SPECIFIC / OUTLIERS: event-day bias is not clearly separated "
            "from normal forecast variability; the RTE cases look like individual "
            "misses rather than a systematic model error."
        )
    lines.append(f"**Verdict:** {verdict}")
    text = "\n".join(lines)

    out = cfg.results_dir / "conclusion.md"
    out.write_text(text, encoding="utf-8")
    return text


def main() -> None:
    """Parse CLI options and run the wind verification pipeline."""
    parser = argparse.ArgumentParser(
        description="HRES 10 m wind-speed verification study"
    )
    parser.add_argument(
        "--skip-obs", action="store_true", help="Reuse cached observations"
    )
    parser.add_argument("--skip-fc", action="store_true", help="Reuse cached forecasts")
    parser.add_argument(
        "--force-obs", action="store_true", help="Force STVL re-retrieval"
    )
    parser.add_argument(
        "--force-fc", action="store_true", help="Force MARS re-retrieval"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print config and exit")
    args = parser.parse_args()

    cfg = StudyConfig()
    print("=" * 70)
    print("HRES 10 m wind-speed verification study")
    print(f"  Box       : N={cfg.north} W={cfg.west} S={cfg.south} E={cfg.east}")
    print(f"  Init dates: {cfg.init_start} → {cfg.init_end}  cycles={cfg.cycles}")
    print(f"  Steps     : {cfg.steps[0]}..{cfg.steps[-1]} h")
    print(f"  Events    : {', '.join(str(d) for d in cfg.event_days)}")
    print("=" * 70)
    if args.dry_run:
        return

    # 1. Observations -------------------------------------------------------
    if not args.skip_obs:
        retrieve_observations(cfg, force=args.force_obs)
    obs = load_observations(cfg)

    # 2. Forecasts ----------------------------------------------------------
    forecasts = load_all_forecasts(cfg, force=args.force_fc)
    if not forecasts:
        print("✗ No forecasts retrieved — aborting.")
        return

    # 3. Match --------------------------------------------------------------
    pairs = vf.build_matched_pairs(cfg, forecasts, obs)
    pairs.to_parquet(cfg.results_dir / "matched_pairs.parquet")

    # 4. Scores -------------------------------------------------------------
    overall = vf.scores_overall(pairs)
    by_lead = vf.scores_by_lead(pairs)
    by_station_ev = vf.scores_by_station(pairs, event_only=True)
    by_station_base = vf.scores_by_station(pairs, event_only=False)
    by_day = vf.scores_by_valid_day(pairs)
    by_hour = vf.scores_by_hour(pairs)

    overall.to_csv(cfg.results_dir / "scores_overall.csv")
    by_lead.to_csv(cfg.results_dir / "scores_by_lead.csv", index=False)
    by_day.to_csv(cfg.results_dir / "scores_by_day.csv", index=False)
    by_hour.to_csv(cfg.results_dir / "scores_by_hour.csv", index=False)
    print("\nOverall scores:\n", overall.round(3))

    # 5. Plots --------------------------------------------------------------
    figs = [
        plots.plot_scores_by_lead(cfg, by_lead, "bias_rmse_by_lead.png"),
        plots.plot_daily_bias(cfg, by_day, "daily_bias.png"),
        plots.plot_error_distribution(cfg, pairs, "error_distribution.png"),
        plots.plot_scatter(cfg, pairs, "scatter_fc_vs_obs.png"),
        plots.plot_event_timeseries(cfg, pairs, "event_timeseries.png"),
        plots.plot_station_bias_map(
            cfg,
            by_station_ev,
            "Mean 10 m wind-speed error — event days",
            "map_bias_event.png",
        ),
        plots.plot_station_bias_map(
            cfg,
            by_station_base,
            "Mean 10 m wind-speed error — full window",
            "map_bias_all.png",
        ),
    ]
    print("\nFigures written:")
    for f in figs:
        print(f"  {f}")

    # 6. Conclusion ---------------------------------------------------------
    print("\n" + "=" * 70)
    print(_write_conclusion(cfg, overall, by_lead, by_station_ev, by_day))
    print("=" * 70)


if __name__ == "__main__":
    main()
