# PhaseSight Validation Kit (prototype 0.1)

This is the first executable measurement prototype for PhaseSight. It is intentionally narrower than the final product: it estimates **2-D translational motion in pixels** from a selected machine region relative to a selected static background region, then estimates the dominant frequency with Welch's power spectral density.

It is a measurement-screening prototype, not an ISO-compliant vibration meter and not a fault classifier. It does not convert pixels to mm, mm/s, acceleration, or remaining useful life.

## What this prototype does

1. Reads a constant-frame-rate video.
2. Converts each frame to grayscale.
3. Uses a static **anchor ROI** to estimate common camera translation.
4. Uses a **target ROI** to estimate the apparent machine translation.
5. Subtracts anchor translation from target translation to estimate motion relative to the background.
6. Builds X/Y displacement traces in pixels.
7. Uses SciPy Welch PSD to estimate the dominant frequency, spectral prominence and a provisional 2x-harmonic ratio.
8. Saves CSV, PNG plots and a JSON summary.

OpenCV `phaseCorrelate` estimates translational shifts using the Fourier shift theorem; the optional Hanning window reduces edge effects. The reference arrays are copied before every call because the implementation should not be allowed to alter the persistent reference buffers. SciPy's Welch method averages modified periodograms from overlapping segments.

## Requirements

- Python 3.11 or newer
- OpenCV, NumPy, SciPy, Matplotlib
- pytest for the test suite

The code in this delivery was run in a Python 3.13.5 environment with OpenCV 4.13.0, NumPy 2.3.5, SciPy 1.17.0 and pytest 9.0.2. Your Mac's installed Python version may differ; use an isolated environment and check the package installation before changing the global Python setup.

## Install on macOS

Open Terminal and move into this folder:

```bash
cd PhaseSight_Validation_Kit
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

If the `python3` command points to an interpreter for which OpenCV/SciPy wheels are unavailable, use a supported Homebrew Python interpreter (Python 3.13 is the version used for this validation run) to create the environment. Do not install packages into the system interpreter.

## 1. Run the automated tests

```bash
pytest -q
```

The tests cover:

- recovery of a known sub-pixel sinusoidal translation;
- rejection of common camera translation using an anchor ROI;
- checking that repeated phase-correlation calls do not corrupt the stored reference images;
- dominant-frequency estimation;
- detection of an added second harmonic;
- low-signal handling;
- invalid ROI and timestamp checks;
- baseline/current change comparison.

## 2. Run the synthetic validation suite

```bash
phasesight validate --json validation_results.json
```

The suite generates deterministic images in memory and tests clean vibration, camera shake plus vibration, a camera-shake-only null control, and an added 2x harmonic. It prints the estimated frequency, displacement RMSE and trace correlation.

These are algorithm tests using simulated image motion. They are **not** proof that a physical webcam will reach the same accuracy.

## 3. Generate additional sample clips (optional)

The three pre-generated 10-second H.264 examples are already included in `data/portable/`: `baseline.mp4`, `changed.mp4`, and `camera_only.mp4`. Their reference outputs are in the matching `out_*` folders.

To generate new clips with different parameters, use:

```bash
phasesight generate-synthetic data/generated/baseline.mp4 --frequency 8.5 --amplitude 0.22 --fps 60 --duration 10 --camera-shake 0.65 --noise 1.5 --seed 7
phasesight generate-synthetic data/generated/changed.mp4 --frequency 8.5 --amplitude 0.36 --second-harmonic 0.10 --fps 60 --duration 10 --camera-shake 0.65 --noise 1.5 --seed 7
phasesight generate-synthetic data/generated/camera_only.mp4 --frequency 8.5 --amplitude 0 --fps 60 --duration 10 --camera-shake 0.65 --noise 1.5 --seed 7
```

The generated scene is 640x360. The default target ROI is `360,110,160,160`; the default anchor ROI is `60,100,160,160`.

## 4. Inspect a video

```bash
phasesight inspect data/portable/baseline.mp4 \
  --target 360,110,160,160 \
  --anchor 60,100,160,160 \
  --out output/baseline \
  --min-frequency 1 --max-frequency 20 --nperseg 256
```

Outputs:

- `*_motion.csv`: per-frame target, anchor and relative displacement;
- `*_spectrum.png`: displacement trace and Welch spectra;
- `*_summary.json`: frequency, RMS displacement in pixels, spectral prominence and quality status.

To compare two inspections, analyse both clips and run:

```bash
phasesight compare output/baseline/baseline_summary.json \
  output/changed/changed_summary.json --axis x --out output/comparison.json
```

The labels `WARNING_CHANGE` and `ALERT_CHANGE` mean that the signal changed against the chosen baseline. They do not identify a bearing defect or prove that a machine is unsafe. An axis is not compared when the signal is low or when a matching strong peak is present in the anchor. A matching peak is reported as `CONTAMINATED`; a weak/unreliable peak is reported as `LOW_SIGNAL`.

For a more conservative comparison, capture a machine-off/no-motion clip using the same camera position and settings, inspect it, then supply its summary as a noise-floor reference:

```bash
phasesight compare baseline_summary.json current_summary.json \
  --axis x --noise-floor-summary machine_off_summary.json \
  --noise-floor-multiple 3 --out comparison.json
```

This requires both the baseline and current RMS displacement to be at least 3 times the measured machine-off RMS for that axis. The multiplier is provisional and should be calibrated with real recordings.

### Multi-run statistical baseline screening

To aggregate $\ge 3$ healthy baseline captures into an immutable statistical `BaselineRecord` using Median and scaled MAD:

```bash
phasesight build-baseline run1_summary.json run2_summary.json run3_summary.json \
  --asset-id "motor_01" --out baseline_motor.json
```

To screen a current inspection against the statistical baseline:

```bash
phasesight assess current_summary.json baseline_motor.json --axis x --threshold 3.0
```

The assessment evaluates:
- **Confidence Gate:** Verifies `signal_quality == 'VALID'` and confirms no anchor contamination.
- **Review Gate:** Standardized robust deviation $z = \frac{x - \text{median}}{1.4826 \cdot \text{MAD} + \epsilon}$ against threshold (default 3.0), classifying the capture as `Normal`, `Review`, or `Low confidence`.

## 5. Local inspection UI (Streamlit)

For an interactive workbench, launch the local-first Streamlit interface:

```bash
phasesight ui
```

Or run Streamlit directly:

```bash
streamlit run phasesight/app.py
```

The UI provides:

1. **Video Selection / Upload:** Choose from the pre-packaged sample clips (`baseline.mp4`, `changed.mp4`, `camera_only.mp4`) or upload any custom MP4, AVI, or MOV video.
2. **First Frame Preview & ROI Configuration:** Visual preview of the first video frame with live-rendered Target ROI (green box) and Static Anchor ROI (orange box).
3. **Automated ROI Validation:** Verifies that both regions are within frame bounds, non-overlapping, at least 32×32 pixels, and have sufficient image texture/contrast (pixel intensity standard deviation ≥ 2.0).
4. **Analysis Parameter Control:** Configure FPS override (optional), frequency band (`min_frequency` and `max_frequency`), and Welch segment length (`nperseg`).
5. **Measurement Execution:** Runs the exact same `analyse_video` pipeline without duplicated logic.
6. **Results & Spectra Display:** Displays dominant frequency, RMS displacement in pixels, spectral prominence (dB), 2x harmonic ratio, anchor-contamination check, and the generated displacement/PSD plots.
7. **Direct Downloads:** Export the per-frame displacement CSV, spectrum PNG plot, and summary JSON.
8. **Baseline Comparison:** Compare the current measurement against a baseline (or uploaded JSON summaries) using `compare_inspection_summaries` to flag `WARNING_CHANGE`, `ALERT_CHANGE`, `NO_MAJOR_CHANGE`, or `INSUFFICIENT_SIGNAL`.

## 6. Select ROIs in your own video

Use the included OpenCV selection tool:

```bash
python scripts/select_rois.py /path/to/your_video.mp4 --output rois.json
```

Select the target ROI first, then a separate static anchor ROI. The script prints both boxes in `x,y,width,height` format. Paste those values into the `--target` and `--anchor` arguments for `phasesight inspect`.

ROI guidance:

- Target: a rigid, textured, stationary-looking surface on the machine (housing edge, bolt pattern, casing seam), not a spinning blade.
- Anchor: a stationary wall, pillar or rigid structure in the same view.
- Keep boxes separate, at least 32x32 pixels, well lit and sharply focused.
- Do not place the anchor on another vibrating machine.

## 7. Recommended real-world test order

### A. Synthetic videos first

Use the included clips and confirm that the tool returns approximately 8.5 Hz in the moving target. The encoded camera-only/null sample should be rejected as non-valid (`CONTAMINATED` when a strong same-frequency peak also appears in the anchor, or `LOW_SIGNAL` when no reliable peak is present). The baseline-vs-null comparison should return `INSUFFICIENT_SIGNAL`. This validates the installed code and the analysis chain before camera setup becomes a variable.

### B. Public benchmark videos second

Use an actual video plus the paired reference sensor data where possible. Recommended starting points:

- **Rotor camera + eddy-current displacement benchmark (Mendeley Data):** https://data.mendeley.com/datasets/47y7rwc2yg/1 . This includes 500 FPS rotor videos and synchronized eddy-current displacement sensor data sampled at 1 kHz, with healthy/unbalance operating cases. Start with one 1000 RPM clip and its matching CSV. The dataset page lists CC BY 4.0. See its README for synchronization, calibration and naming details.
- **Motion Magnification by DMD (Zenodo):** https://zenodo.org/records/18021913 . This includes raw stationary-camera structural videos, including a 240 FPS three-story lab structure and 25 FPS footbridge recordings. It is useful for a second, structural-motion test, but not as direct machine-bearing ground truth.
- **MIT Phase-Based Video Motion Processing:** https://people.csail.mit.edu/nwadhwa/phase-video/ . This is the original research page with engine-vibration examples, paper, code and supplemental videos. Use it to compare visual behaviour and understand phase-based magnification; some downloads are large.

Do not download a multi-gigabyte dataset for the first pass. Start with one small raw video and its matching sensor file. The current CLI accepts ordinary decoded video; it does not yet parse event-camera `.dat` data.

### C. Your ceiling fan as an exploratory test

You can test on your ceiling fan, but treat it as a **repeatability and signal-quality experiment**, not a calibrated ground-truth test.

1. Put the phone on a stable tripod or fixed support, at a safe distance. Do not hand-hold it.
2. Record a 10-15 second fan-OFF clip first. Keep the camera, zoom, focus and exposure unchanged.
3. Select a textured region on the fixed motor housing/canopy or a clear mounting feature. Select a separate ceiling region for the anchor. Do not track the spinning blades for this first test.
4. Record a 10-15 second fan-ON clip at one fixed speed. Repeat it three times without moving the camera.
5. Try another fixed speed, again without moving the camera.
6. Compare the traces, dominant peaks, `LOW_SIGNAL`/`VALID` state and run-to-run variation.

Safety: never touch, attach tape/weights/markers to, or adjust a running fan. Do not put a tripod or object in the fan's sweep. If the motor housing is too smooth, distant or visually stationary, the result may correctly be `LOW_SIGNAL`; that is not necessarily a software failure.

For a useful 60 FPS analysis, the Nyquist limit is 30 Hz. In practice we should stay below that limit with margin, and use a higher-frame-rate recording for faster components. Do not interpret a peak above Nyquist or infer a blade/bearing fault from one frequency peak.

## Current limitations (known and intentional)

- Translation only: no rotation, perspective, zoom or rolling-shutter correction.
- The anchor removes common translation only; it does not correct camera rotation or parallax.
- The target needs texture and sufficient image contrast.
- Motion blur, autofocus, auto-exposure, rolling shutter, compression, flicker and occlusion can reduce measurement quality.
- The current trace is measured in pixels. Converting to millimetres requires scene-scale calibration and geometry; velocity requires calibrated displacement and a validated time derivative.
- The 10 dB spectral prominence gate and same-frequency anchor check are provisional. Calibrate them from actual no-motion/null recordings before product use.
- Compression and lighting modulation can create narrowband artefacts. The anchor-frequency check catches a shared peak when it appears in both regions, but it is not a universal flicker-removal algorithm.
- Baseline thresholds are screening thresholds, not diagnostic standards.
- The current implementation is an offline video prototype, not a live webcam UI.

## Acceptance criteria before adding the UI

1. All unit tests pass on the target Mac.
2. Synthetic 8.5 Hz signal: estimated peak is within the larger of 0.5 Hz or one Welch bin; displacement correlation >= 0.85 under the tested camera shake.
3. Camera-only/null video: quality gate returns a non-valid status (`LOW_SIGNAL` or `CONTAMINATED`) and does not publish its random PSD peak as a valid vibration frequency.
4. Added 2x component: measured 2x/fundamental power ratio increases compared with the no-harmonic control.
5. A real benchmark clip: compare video-derived displacement/frequency with its paired sensor data after confirming time alignment and ROI suitability.
6. Ceiling fan: three repeated captures at the same speed give a stable result or clearly report low signal; do not claim physical calibration from this test.

Only after these pass should we add the Streamlit workbench, baseline storage and maintenance log. Riesz motion magnification should remain a separate visual branch until it is independently implemented and tested.
