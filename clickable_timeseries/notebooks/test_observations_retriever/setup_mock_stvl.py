#!/usr/bin/env python3
"""Realistic Mock STVL executable that behaves exactly like the real stvl_getgeo tool.

This will reveal if the ObservationsRetriever class has any issues.
"""

import argparse
import math
import os
import random
import sys
import time
from datetime import datetime, timedelta


def generate_realistic_stations():
    """Generate realistic European weather stations."""
    stations = []
    station_data = [
        ("06260", 49.9667, 3.0167, 156),
        ("07020", 50.0333, 8.5667, 112),
        ("06190", 48.7167, 2.3667, 89),
        ("03772", 52.4667, 13.4000, 48),
        ("08181", 47.2667, 11.3833, 574),
        ("16245", 45.8167, 15.9667, 123),
        ("02527", 59.9167, 10.7167, 94),
        ("06610", 43.6500, 3.9167, 59),
        ("08495", 48.2500, 16.3667, 183),
        ("16320", 45.0167, 7.6333, 239),
    ]

    for station_id, lat, lon, elevation in station_data:
        stations.append(
            {"id": station_id, "lat": lat, "lon": lon, "elevation": elevation}
        )

    for i in range(50, 80):
        lat = 35.0 + 25.0 * random.random()
        lon = -10.0 + 35.0 * random.random()
        elevation = random.randint(0, 1500)
        stations.append(
            {"id": f"{i:05d}", "lat": lat, "lon": lon, "elevation": elevation}
        )

    return stations


def generate_parameter_values(parameter, datetime_obj):  # noqa: PLR0911
    """Generate realistic values for each parameter."""
    if parameter == "2t":
        hour = datetime_obj.hour
        base_temp = 285.0 + 8 * random.random()
        daily_cycle = 3 * math.cos((hour - 14) * math.pi / 12)
        return base_temp + daily_cycle + random.gauss(0, 1)

    elif parameter == "2d":
        hour = datetime_obj.hour
        base_dewpoint = 275.0 + 6 * random.random()
        daily_cycle = 2 * math.cos((hour - 6) * math.pi / 12)
        return base_dewpoint + daily_cycle + random.gauss(0, 0.5)

    elif parameter == "tp":
        if random.random() > 0.8:  # noqa: PLR2004
            return random.expovariate(1000.0)
        return 0.0

    elif parameter == "10ff":
        base_wind = 3.0 + 7 * random.random()
        return max(0, base_wind + random.gauss(0, 1.5))

    elif parameter == "10fg":
        base_gust = 8.0 + 12 * random.random()
        return base_gust + random.expovariate(0.3)

    elif parameter == "tmax":
        return 288.0 + 12 * random.random() + random.gauss(0, 2)

    elif parameter == "tmin":
        return 275.0 + 8 * random.random() + random.gauss(0, 1.5)

    else:
        return random.gauss(0, 1)


def create_geo_files(output_dir, parameter, start_date, end_date, times, period=None):  # noqa: ARG001, PLR0913
    """Create geo files as the real STVL would."""
    start_dt = datetime.strptime(start_date, "%Y%m%d")
    end_dt = datetime.strptime(end_date, "%Y%m%d")

    time_hours = [int(t) for t in times.split()]

    stations = generate_realistic_stations()

    current_date = start_dt
    file_count = 0

    while current_date <= end_dt:
        for hour in time_hours:
            dt = current_date.replace(hour=hour, minute=0, second=0)

            timestamp = dt.strftime("%Y%m%d%H%M%S")
            filename = f"geo{parameter}_{timestamp}"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, "w") as f:
                for station in stations:
                    if random.random() > 0.1:  # noqa: PLR2004
                        value = generate_parameter_values(parameter, dt)
                        f.write(
                            f"{station['id']} {station['lat']:.6f} {station['lon']:.6f} "
                            f"{station['elevation']} {value:.6f}\n"
                        )

            file_count += 1
        current_date += timedelta(days=1)

    return file_count


def main():  # noqa: D103, PLR0915
    parser = argparse.ArgumentParser(description="STVL getgeo", add_help=False)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--parameter", required=True)
    parser.add_argument("--dates", required=True)
    parser.add_argument("--times", required=True)
    parser.add_argument("--period", type=int)
    parser.add_argument("--columns", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--flattree", action="store_true")

    try:
        args = parser.parse_args()
    except SystemExit:
        sys.exit(2)

    if not os.path.exists(os.path.dirname(args.outdir)) and os.path.dirname(
        args.outdir
    ):
        print(f"Error: Parent directory of {args.outdir} does not exist")
        sys.exit(1)

    try:
        if "/to/" not in args.dates:
            print("Error: Invalid date format. Expected YYYYMMDD/to/YYYYMMDD")
            sys.exit(1)
        start_date, end_date = args.dates.split("/to/")

        datetime.strptime(start_date, "%Y%m%d")
        datetime.strptime(end_date, "%Y%m%d")
    except ValueError:
        print("Error: Invalid date format")
        sys.exit(1)

    try:
        time_hours = [int(t) for t in args.times.split()]
        for hour in time_hours:
            if not 0 <= hour <= 23:  # noqa: PLR2004
                print(f"Error: Invalid hour {hour}")
                sys.exit(1)
    except ValueError:
        print("Error: Invalid times format")
        sys.exit(1)

    valid_params = ["2t", "2d", "tp", "10ff", "10fg", "tmax", "tmin"]
    if args.parameter not in valid_params:
        print(f"Error: Unknown parameter {args.parameter}")
        sys.exit(1)

    period_params = ["tp", "10fg", "tmax", "tmin"]
    if args.parameter in period_params and not args.period:
        print(f"Error: Parameter {args.parameter} requires --period")
        sys.exit(1)

    if args.parameter not in period_params and args.period:
        print(f"Warning: Parameter {args.parameter} does not use --period (ignored)")

    os.makedirs(args.outdir, exist_ok=True)

    print(f"Retrieving {args.parameter} from {args.sources}")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Times: {args.times}")
    if args.period:
        print(f"Period: {args.period} hours")

    time.sleep(0.5)

    try:
        file_count = create_geo_files(
            args.outdir, args.parameter, start_date, end_date, args.times, args.period
        )
        print(f"Created {file_count} files in {args.outdir}")

    except Exception as e:
        print(f"Error during retrieval: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
