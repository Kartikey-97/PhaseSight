# Start here

1. Read `README.md` for installation and command examples.
2. Read `TEST_REPORT.md` for exactly what has and has not been verified.
3. Run `pytest -q`.
4. Run `phasesight validate --json data/validation_results.json`.
5. Inspect the included baseline, changed and camera-only MP4 files as shown below.

```bash
phasesight inspect data/portable/baseline.mp4 --target 360,110,160,160 --anchor 60,100,160,160 --out output/baseline --min-frequency 1 --max-frequency 20 --nperseg 256
phasesight inspect data/portable/changed.mp4 --target 360,110,160,160 --anchor 60,100,160,160 --out output/changed --min-frequency 1 --max-frequency 20 --nperseg 256
phasesight inspect data/portable/camera_only.mp4 --target 360,110,160,160 --anchor 60,100,160,160 --out output/camera_only --min-frequency 1 --max-frequency 20 --nperseg 256
```

Compare baseline with changed:

```bash
phasesight compare output/baseline/baseline_summary.json output/changed/changed_summary.json --axis x --out output/baseline_vs_changed.json
```

Compare baseline with the camera-only null clip:

```bash
phasesight compare output/baseline/baseline_summary.json output/camera_only/camera_only_summary.json --axis x --out output/baseline_vs_null.json
```

A `WARNING_CHANGE` result is a change in measured motion, not a fault diagnosis. A null or contaminated signal should not be treated as a healthy machine or a fault.
