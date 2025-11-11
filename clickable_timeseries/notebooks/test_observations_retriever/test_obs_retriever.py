#!/usr/bin/env python3
"""Test script for the observation retrieval interface using mock STVL.

This script tests the complete workflow from parameter selection to data visualization.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))


def test_observations_retriever():
    """Test the ObservationsRetriever class with mock STVL."""
    print("Testing ObservationsRetriever class...")

    # Determine STVL path
    home_bin = Path.home() / "bin" / "stvl_getgeo"
    current_dir = Path.cwd() / "stvl_getgeo"

    if home_bin.exists():
        stvl_path = str(home_bin)
        print(f"Using STVL from ~/bin: {stvl_path}")
    elif current_dir.exists():
        stvl_path = str(current_dir)
        print(f"Using STVL from current directory: {stvl_path}")
    else:
        print("Mock STVL not found. Please run the setup script first.")
        return False

    try:
        from helpers.observations_retriever import ObservationsRetriever

        retriever = ObservationsRetriever(stvl_path)

        # Test parameter info
        print("\nTesting parameter information:")
        for param in ["2t", "tp", "10ff", "tmax"]:
            info = retriever.get_parameter_info(param)
            print(f"  {param}: {info['type']} parameter")

        # Test retrieval with a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"\nTesting data retrieval to: {temp_dir}")

            # Test instantaneous parameter
            result = retriever.retrieve(
                sources="synop",
                parameter="2t",
                start_date="20250301",
                end_date="20250302",
                output_dir=os.path.join(temp_dir, "2t_test"),
            )

            if result["success"]:
                print("✅ Temperature (2t) retrieval successful")
                files = list(Path(result["output_dir"]).glob("geo*"))
                print(f"   Created {len(files)} data files")
            else:
                print("❌ Temperature retrieval failed")
                return False

            # Test period-based parameter
            result = retriever.retrieve(
                sources="synop",
                parameter="tp",
                period=24,
                start_date="20250301",
                end_date="20250302",
                output_dir=os.path.join(temp_dir, "tp_test"),
            )

            if result["success"]:
                print("✅ Precipitation (tp) retrieval successful")
                files = list(Path(result["output_dir"]).glob("geo*"))
                print(f"   Created {len(files)} data files")
            else:
                print("❌ Precipitation retrieval failed")
                return False

        print("✅ ObservationsRetriever tests passed!")
        return True

    except Exception as e:
        print(f"❌ Error testing ObservationsRetriever: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_station_loading():
    """Test station loading and processing."""
    print("\nTesting station data loading...")

    try:
        from helpers.stations_manipulating import StationCreator

        # Create test data directory
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"Creating test files in: {temp_dir}")

            test_files = [
                "10fg_obs_20250301000.geo",
                "10fg_obs_20250301060.geo",
                "10fg_obs_20250301120.geo",
            ]

            for filename in test_files:
                filepath = os.path.join(temp_dir, filename)
                print(f"Creating file: {filepath}")
                with open(filepath, "w") as f:
                    f.write("#GEO\n")
                    f.write("#FORMAT NCOLS\n")
                    f.write("#COLUMNS\n")
                    f.write(
                        "stnid\tlatitude\tlongitude\tlevel\tdate\ttime\tvalue_0\t\n"
                    )
                    f.write(
                        "# Missing values represented by 3e+38 (not user-changeable)\n"
                    )
                    f.write("#METADATA\n")
                    f.write("date=20250301\n")
                    f.write("level=0\n")
                    f.write("leveltype=sfc\n")
                    f.write("param=10fg\n")
                    f.write("parameter=10fg\n")
                    f.write("time=0000\n")
                    f.write("units=m/s\n")
                    f.write("#DATA\n")

                    test_stations = [
                        ("33000001", 50.136, 1.834, 5.1),
                        ("33000003", 48.98317, 2.126, 6.6),
                        ("33000004", 42.97283, -0.072167, 1.7),
                        ("33000005", 48.97933, 6.243167, 3.7),
                        ("33000006", 44.17217, 0.594667, 1.8),
                    ]

                    for stnid, lat, lon, value in test_stations:
                        f.write(f"{stnid}\t{lat}\t{lon}\t0\t20250301\t0\t{value}\n")

            station_creator = StationCreator()

            try:
                from helpers.stations_manipulating import GeoDataProcessor

                geo_processor = GeoDataProcessor()
                geo_files = geo_processor.get_geo_files(temp_dir)
                print(f"Geo files found by GeoDataProcessor: {geo_files}")
            except Exception as e:
                print(f"Error with GeoDataProcessor: {e}")

            stations_gdf = station_creator.create_stations_geodataframe(temp_dir)

            if stations_gdf is not None and len(stations_gdf) > 0:
                print(f"✅ Successfully loaded {len(stations_gdf)} stations")
                print(f"   Station IDs: {list(stations_gdf.index)}")
                return True
            else:
                print("❌ Failed to load stations")
                print(f"   Returned: {stations_gdf}")
                return False

    except Exception as e:
        print(f"❌ Error testing station loading: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_ui_integration():
    """Test basic UI integration points."""
    print("\nTesting UI integration points...")

    try:
        from helpers.widgets.user_interface.widget_configuration import (
            WidgetConfiguration,
        )

        config = WidgetConfiguration()
        widgets = config.get_widgets()

        # Check that observation-related widgets exist
        obs_widgets = [
            "has_observations",
            "retrieve_observations",
            "obs_folder_path_input",
            "stvl_path",
        ]

        missing_widgets = []
        for widget_name in obs_widgets:
            if widget_name not in widgets:
                missing_widgets.append(widget_name)

        if missing_widgets:
            print(f"❌ Missing widgets: {missing_widgets}")
            return False
        else:
            print("✅ All observation widgets present")

        from helpers.widgets.timeseries_user_interface import TimeseriesUI

        ui = TimeseriesUI()
        if hasattr(ui, "widgets") and "stvl_path" in ui.widgets:
            print("✅ UI initialization successful")
        else:
            print("❌ UI missing STVL path widget")
            return False

        return True

    except Exception as e:
        print(f"❌ Error testing UI integration: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_parameter_validation():
    """Test parameter validation logic."""
    print("\nTesting parameter validation...")

    try:
        # Test observation parameter detection
        test_paths = {
            "/data/tp/tp_24h": "tp",
            "/data/2t_observations": "2t",
            "/data/wind/10ff": "10ff",
            "/data/temperature/tmax": "tmax",
        }

        for path, expected_param in test_paths.items():
            detected = detect_parameter_from_path(path)
            if detected == expected_param:
                print(f"✅ Parameter detection: {path} -> {detected}")
            else:
                print(
                    f"❌ Parameter detection failed: {path} -> {detected} (expected {expected_param})"
                )

        return True

    except Exception as e:
        print(f"❌ Error testing parameter validation: {e}")
        return False


def detect_parameter_from_path(path):
    """Test parameter detection for testing."""
    params = ["10ff", "10fg", "2d", "2t", "tp", "tmin", "tmax"]
    params = sorted(params, key=len, reverse=True)

    path_lower = path.lower()
    for param in params:
        if param in path_lower:
            return param
    return None


def run_integration_test():
    """Run a complete integration test."""
    print("\n" + "=" * 60)
    print("RUNNING COMPLETE INTEGRATION TEST")
    print("=" * 60)

    tests = [
        ("ObservationsRetriever", test_observations_retriever),
        ("Station Loading", test_station_loading),
        ("UI Integration", test_ui_integration),
        ("Parameter Validation", test_parameter_validation),
    ]

    results = {}

    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results[test_name] = False

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for result in results.values() if result)
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:<25} {status}")

    print(f"\nOverall: {passed}/{total} tests passed")


def main():
    """Main test function."""  # noqa: D401
    print("This script tests the observation retrieval interface with mock STVL")

    # Check if mock STVL exists
    home_bin = Path.home() / "bin" / "stvl_getgeo"
    current_dir = Path.cwd() / "stvl_getgeo"

    if not (home_bin.exists() or current_dir.exists()):
        print("\n❌ Mock STVL not found!")
        print("Please run the setup script first to install the mock STVL executable.")
        print("\nRun: python setup_mock_stvl.py")
        return

    run_integration_test()


if __name__ == "__main__":
    main()
