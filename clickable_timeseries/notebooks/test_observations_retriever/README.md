# Observation Retrieval Test Suite

This test suite validates the weather observation retrieval interface using a mock STVL executable.

## Quick Setup & Test

Run these three commands to set up and test the observation retrieval system:

```bash
# 1. Install the mock STVL executable
cp setup_mock_stvl.py ~/bin/stvl_getgeo
chmod +x ~/bin/stvl_getgeo

# 2. Run the test suite
python test_obs_retriever.py
```

## Expected Results

A successful test run should show:

```
============================================================
TEST SUMMARY
============================================================
ObservationsRetriever     ✅ PASS
Station Loading           ✅ PASS
UI Integration            ✅ PASS
Parameter Validation      ✅ PASS
Overall: 4/4 tests passed
```

## Test Components

### ✅ ObservationsRetriever (SHOULD PASS)
Tests the core observation retrieval functionality:
- **2t (Temperature)**: Retrieves instantaneous 3-hourly temperature data
- **tp (Precipitation)**: Retrieves 24-hour accumulated precipitation data
- Validates parameter-specific command construction
- Tests both instantaneous and period-based parameters

**Success indicators:**
- Creates 16 temperature files (2 days × 8 times per day)
- Creates 2 precipitation files (2 days × 1 time per day for 24h accumulation)

### ✅ Station Loading (SHOULD PASS)
Tests station data loading from geo files:
- Creates mock geo files with proper STVL format and naming convention
- Tests StationCreator with realistic `param_obs_YYYYMMDDHHMM.geo` files
- Validates that station data can be parsed from the correct file format

**Success indicators:**
- Successfully loads station information from geo files
- Creates geodataframe with station coordinates and IDs
- File format matches real STVL output structure

### ✅ UI Integration (SHOULD PASS)
Validates UI widget configuration:
- Checks for required observation widgets
- Tests TimeseriesUI initialization
- Verifies STVL path widget exists

### ✅ Parameter Validation (SHOULD PASS)
Tests parameter detection from folder paths:
- Validates detection of weather parameters from file paths
- Tests pattern matching for common observation folder structures

## Interpreting Results

### Success (4/4 tests passing)
Your observation retrieval system is working correctly if you see:
- ✅ ObservationsRetriever PASS
- ✅ Station Loading PASS
- ✅ UI Integration PASS  
- ✅ Parameter Validation PASS

All tests passing indicates the complete observation system is functional.
