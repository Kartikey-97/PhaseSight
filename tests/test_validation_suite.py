from phasesight.validation import run_validation_suite


def test_deterministic_validation_suite_passes():
    results = run_validation_suite()
    assert len(results) == 4
    assert all(result["status"] == "PASS" for result in results)
    null_case = next(result for result in results if "null control" in result["name"])
    assert null_case["signal_quality"] == "LOW_SIGNAL"
    harmonic_case = next(result for result in results if "2x harmonic" in result["name"])
    clean_case = next(result for result in results if result["name"] == "clean target vibration")
    assert harmonic_case["second_harmonic_ratio"] > clean_case["second_harmonic_ratio"] * 10
