# PhaseSight validation report

**Run date:** 14 November 2026  
**Implementation tested:** PhaseSight validation prototype v0.1.0  
**Environment:** Python 3.13.5, OpenCV 4.13.0, NumPy 2.3.5, SciPy 1.17.0, Matplotlib 3.10.8, pytest 9.0.2  
**Test status:** 14 automated tests passed; 4 deterministic synthetic validation scenarios passed; 3 compressed synthetic MP4s were analysed end-to-end.

## What was tested

The tested prototype is a **translation-based vibration-screening pipeline**. It estimates target ROI movement with OpenCV phase correlation, estimates common movement in a separate static anchor ROI, subtracts the anchor movement from the target movement, and analyses the resulting pixel-displacement trace with SciPy Welch PSD.

It is not yet the full PhaseSight product. In particular, this tested version does not implement the Riesz pyramid, motion magnification, live camera UI, physical calibration to millimetres, bearing-fault diagnosis, remaining-useful-life estimation, or ISO severity classification.

## 1. Automated test suite

Command:

```bash
pytest -q
```

Result:

```text
..............                                                           [100%]
14 passed
```

Coverage includes:

- sub-pixel translation recovery on synthetic frames;
- common camera translation cancellation using a background anchor;
- protection of stored reference frames during repeated phase-correlation calls;
- invalid, overlapping and out-of-frame ROI handling;
- known-frequency estimation and timestamp validation;
- second-harmonic comparison;
- low-signal rejection;
- Nyquist aliasing demonstration;
- contamination detection when a strong peak is shared with the anchor ROI;
- MP4 encode/decode round-trip and output-file creation;
- null-video quality rejection.

## 2. Deterministic synthetic-frame validation

All cases use 60 FPS simulated imagery with known target displacement. The clean and camera-shake cases use a target frequency of 8.5 Hz.

| Scenario | Measured peak | Frequency error | Displacement RMSE | Correlation | Result |
|---|---:|---:|---:|---:|---|
| Clean target vibration | 8.5036 Hz | 0.0036 Hz | 0.0539 px | 0.9912 | PASS |
| Camera shake + target vibration | 8.5038 Hz | 0.0038 Hz | 0.1370 px | 0.9014 | PASS |
| Camera shake only (null) | No valid target signal | — | 0.0584 px residual RMSE | — | PASS: LOW_SIGNAL |
| Target vibration + 2× harmonic | 8.5026 Hz | 0.0026 Hz | 0.1109 px | 0.9384 | PASS |

The 2× harmonic power ratio increased from approximately 0.000257 in the clean case to 0.06065 in the harmonic case (about 236 times higher in this specific synthetic test). This verifies that the current spectral calculation responds to the deliberately injected harmonic; it does not establish that a real bearing fault can be identified from that ratio.

## 3. Compressed MP4 end-to-end validation

Three 10-second, 640×360, 60 FPS synthetic videos were encoded as MP4 and then decoded and analysed through the same video-analysis pipeline used for user footage. The target ROI was `360,110,160,160`; the static anchor ROI was `60,100,160,160`.

| Clip | X dominant peak | X RMS displacement | X quality | Purpose |
|---|---:|---:|---|---|
| Baseline | 8.5093 Hz | 0.2325 px | VALID | Reference target vibration |
| Changed | 8.5062 Hz | 0.3452 px | VALID | Increased amplitude + added 2× harmonic |
| Camera-only | 20.1563 Hz | 0.0823 px | CONTAMINATED | Environmental/lighting artefact null control |

Baseline-to-changed comparison returned `WARNING_CHANGE`, with a +48.48% RMS displacement change and only 0.0031 Hz dominant-frequency difference. Baseline-to-camera-only comparison returned `INSUFFICIENT_SIGNAL` rather than calling the null clip a valid vibration change.

The camera-only clip includes a simulated 100 Hz illumination modulation. At 60 FPS this can alias to a lower apparent frequency; in the encoded clip a similar peak appears in the target and anchor, so the shared-peak guard rejects it as contaminated. This is a deliberately constructed test, not proof that every kind of light flicker or camera artefact will be rejected.

## 4. Bug found and fixed during testing

Repeated OpenCV phase-correlation calls were degrading the saved reference patches because the correlation routine/windowing path could alter working image data. The tracker now creates fresh normalized patch buffers for each call and has a regression test confirming the stored reference arrays remain unchanged after repeated measurements.

This is an example of why the pipeline is being tested in small layers before building the full interface.

## 5. What these results do and do not prove

**They support:**

- the synthetic translation tracker can recover a known 8.5 Hz target movement;
- the anchor subtraction reduces common translational camera shake in the tested synthetic scene;
- the frequency estimator detects the deliberately added harmonic in the tested signal;
- low-signal and shared-anchor-peak cases can be rejected rather than automatically treated as valid measurements;
- the video encode/decode and output pipeline works on the supplied synthetic MP4s.

**They do not prove:**

- that a normal webcam can resolve the same displacement amplitude on a real motor;
- that the tool measures physical micrometres or mm/s without scene calibration;
- that camera rotation, zoom, perspective, parallax, rolling shutter, motion blur or variable-frame-rate video is corrected;
- that a particular spectral pattern diagnoses a specific machine fault;
- that the system is real-time or production-ready;
- that the current implementation reproduces Riesz/complex-steerable-pyramid phase magnification.

## 6. Required next validation

1. Run the supplied clips on the user's Mac in an isolated Python environment.
2. Record a fixed-camera fan-OFF null clip and three fan-ON repeats at one speed, without touching or modifying the running fan.
3. Use a high-speed rotor benchmark with synchronized displacement-sensor data for quantitative real-world comparison. The recommended Mendeley dataset records high-speed video at 500 FPS alongside eddy-current displacement sensors at 1 kHz; matching video and sensor files are documented by the dataset authors: https://data.mendeley.com/datasets/47y7rwc2yg/1 .
4. Calibrate the signal-quality thresholds on multiple real no-motion and operating clips before relying on alert labels.
5. Only after validation, add the local operator UI and then the optional Riesz visualisation branch.

## Reproducibility commands

```bash
python -m pip install -e '.[dev]'
pytest -q
phasesight validate --json data/validation_results.json
```

Inspect an included clip:

```bash
phasesight inspect data/portable/baseline.mp4 \
  --target 360,110,160,160 \
  --anchor 60,100,160,160 \
  --out output/baseline \
  --min-frequency 1 --max-frequency 20 --nperseg 256
```
