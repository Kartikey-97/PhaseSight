# PhaseSight — Camera-Based Vibration Screening

## Project Vision & Scope
PhaseSight is a local-first software application for campus facilities and small workshops to screen vibration on pumps, ventilation fans, and small motors using standard fixed video. It extracts 2D relative translation (in pixels) using OpenCV phase correlation between a machine region and a static background anchor, analyzes frequency components with SciPy Welch PSD, and detects changes against an asset-specific baseline.

## Non-Negotiable Technical Boundaries
1. **Pixel-Domain Only:** Output is in pixels; no conversion to mm, mm/s, velocity, or acceleration without in-situ calibration.
2. **2D Translation Only:** No claims of correction for camera rotation, perspective, zoom, parallax, or rolling shutter.
3. **Anchor Dependency:** Static anchor removes common camera translation only when stationary and textured.
4. **Screening vs Fault Diagnosis:** Status flags (`Normal`, `Review`, `Low confidence` / `WARNING_CHANGE`, `ALERT_CHANGE`) indicate measured shifts against baseline, not specific mechanical fault diagnosis (bearings, gears, unbalance, RUL).
5. **Separation of Measurement and Magnification:** Riesz motion magnification is an optional visual explanation tool that must never feed the alert calculation.

## Tech Stack
- **Language & Runtime:** Python 3.13 (macOS arm64 / universal)
- **Video & Image Processing:** OpenCV (`cv2.phaseCorrelate`, Hanning window), NumPy
- **Signal Processing:** SciPy (`scipy.signal.welch`, `scipy.signal.detrend`)
- **Workbench:** Streamlit local UI
- **Persistence:** SQLite (`phasesight.db`) + NumPy NPZ (`.npz` for displacement & PSD arrays)
- **Testing:** pytest with synthetic deterministic test matrix
