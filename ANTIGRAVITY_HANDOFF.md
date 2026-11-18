# Antigravity handoff — PhaseSight prototype

## Goal

Continue the PhaseSight project from this tested baseline. Do not replace the working measurement pipeline with an untested rewrite. Work in small, verifiable increments and keep the command-line interface working.

## What currently exists

- `phasesight/tracker.py`: fixed-ROI translation measurement using OpenCV `phaseCorrelate`; target movement minus static-anchor movement.
- `phasesight/analysis.py`: timestamp checks, detrending, Welch PSD, peak interpolation, provisional signal-quality gate, anchor-peak contamination check and baseline comparison helper.
- `phasesight/video.py`: video decoding, per-frame tracking, CSV/PNG/JSON outputs, quality labels for X and Y.
- `phasesight/synthetic.py`: deterministic synthetic video generator with known target displacement, camera shake, lighting modulation and noise.
- `phasesight/validation.py`: four synthetic validation scenarios.
- `phasesight/cli.py`: `validate`, `generate-synthetic`, `inspect`, and `compare` commands.
- `scripts/select_rois.py`: OpenCV GUI for choosing target and anchor rectangles.
- `tests/`: 14 automated tests, currently passing in the reference environment.

Read `README.md` and `TEST_REPORT.md` before changing code.

## Current verified baseline

Reference environment: Python 3.13.5, OpenCV 4.13.0, NumPy 2.3.5, SciPy 1.17.0, Matplotlib 3.10.8, pytest 9.0.2.

The last verification run returned 14 passing tests. The synthetic test suite recovered an 8.5 Hz displacement signal with about 0.004 Hz frequency error and 0.90 correlation under the tested camera shake. The compressed MP4 workflow analysed a known baseline, a changed clip and a camera-only null clip. The baseline-vs-changed result was `WARNING_CHANGE`; baseline-vs-null was `INSUFFICIENT_SIGNAL`.

These are synthetic/software tests only. No user camera or physical motor footage has been measured yet.

## Non-negotiable technical boundaries

- Current measurement output is in **pixels**, not millimetres or mm/s.
- Current tracking is **2D translation only**. Do not claim correction for camera rotation, perspective, zoom, parallax or rolling shutter.
- The static anchor removes common translation only when the anchor is actually stationary and sufficiently textured.
- `WARNING_CHANGE` / `ALERT_CHANGE` means a measured change against baseline, not a diagnosed bearing, gear or shaft fault.
- The signal quality thresholds are provisional and must be configurable and validated on real null clips.
- Current pipeline uses OpenCV phase correlation, not a complex steerable pyramid or a Riesz pyramid.
- Riesz motion magnification is a separate future visualisation feature. Do not claim it exists until implemented and tested independently.
- Do not add ISO compliance, mm/s, RUL prediction, universal 600 Hz sensing or guaranteed rolling-shutter recovery.

## Next development task: local inspection UI

Build a small local-first Streamlit interface. Keep it intentionally simple:

1. Upload a video file.
2. Show the first frame and allow selection of target ROI and static anchor ROI.
3. Validate that the ROIs are in bounds, non-overlapping, at least 32×32 and contain visible texture.
4. Let the operator set FPS override, analysis frequency band and Welch segment length.
5. Run the existing `analyse_video` function without duplicating its signal-processing logic.
6. Display the original video/frame preview, X/Y displacement traces, Welch spectra, peak frequency, pixel RMS and quality status.
7. Allow baseline and current JSON results to be compared using the existing comparison rules.
8. Provide downloads for CSV, PNG and JSON outputs.

Do not add authentication, cloud deployment, multiple services, ML fault classifiers or ERP integrations at this stage.

## Required workflow for every code change

1. Before editing, run `pytest -q` and save the result.
2. Make one small change at a time.
3. Add a test for every new algorithmic behaviour.
4. Run the complete test suite again.
5. Manually run `phasesight validate` and inspect all three included MP4 clips.
6. If a test fails, fix the cause; never delete or weaken a test just to get a green run without documenting why the assertion was invalid.
7. Update README with exact setup and usage steps.
8. Report changed files, tests run, outputs and known limitations. Never invent a successful test run.

## Current command examples

```bash
python -m pip install -e '.[dev]'
pytest -q
phasesight validate --json data/validation_results.json
phasesight inspect data/portable/baseline.mp4 \
  --target 360,110,160,160 \
  --anchor 60,100,160,160 \
  --out output/baseline --min-frequency 1 --max-frequency 20 --nperseg 256
```

## Definition of done for the UI milestone

- UI starts locally from a documented command.
- Upload, ROI selection and analysis work on all three sample clips.
- Baseline clip X-axis is marked valid around 8.5 Hz.
- Changed clip is compared against baseline and returns a change status.
- Camera-only clip is not presented as a valid machine vibration.
- CSV, spectrum image and JSON summary can be downloaded.
- All 14 existing tests plus new UI/helper tests pass.
- No claims of physical calibration or fault diagnosis are introduced.
