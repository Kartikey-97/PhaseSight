# Included synthetic MP4 samples

All three files are synthetic 640x360, 60 FPS, 10-second H.264 MP4 clips. They are generated for testing only and do not depict a real machine.

- `baseline.mp4`: a textured target ROI with a known 8.5 Hz periodic horizontal movement.
- `changed.mp4`: same base frequency, increased displacement amplitude and an added 2x harmonic.
- `camera_only.mp4`: no target vibration; includes simulated camera movement and global lighting modulation to exercise the quality/anchor checks.

The default target ROI is `360,110,160,160`; the default static anchor ROI is `60,100,160,160`.

`out_baseline/`, `out_changed/`, and `out_camera_only/` contain the actual CSV, spectrum PNG, and summary JSON outputs from the latest re-run of the current code. The comparison reports show the baseline-vs-changed and baseline-vs-null outcomes.

These clips verify the software pipeline under controlled conditions. They are not real-world vibration evidence or a substitute for a physical-camera test.
