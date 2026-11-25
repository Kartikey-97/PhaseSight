#!/usr/bin/env python3
"""Generate an executive, light-editorial A4 PDF submission report for PhaseSight Round 3.

Builds a clean, self-contained HTML document (embedding inline vector SVGs and base64
screenshots from reports/e2e_screenshots/) and renders it via Playwright Chromium.

Usage:
  .venv/bin/python scripts/build_round3_pdf.py \
    --video-url "https://youtu.be/PENDING_UPLOAD" \
    --repo-url "https://github.com/PENDING_PUSH" \
    --out docs/PhaseSight_Round3_Submission.pdf
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import html
from pathlib import Path
from playwright.async_api import async_playwright


REPO_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = REPO_ROOT / "reports" / "e2e_screenshots"


def _encode_png_b64(path: Path) -> str:
    """Return a base64 PNG data URI for embedding offline in HTML."""
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _build_html(video_url: str, repo_url: str) -> str:
    safe_video = html.escape(video_url, quote=True)
    safe_repo = html.escape(repo_url, quote=True)

    img_live_500 = _encode_png_b64(SCREENSHOTS_DIR / "01_live_monitor_active.png")
    img_review = _encode_png_b64(SCREENSHOTS_DIR / "06_live_baseline_review.png")
    img_report = _encode_png_b64(SCREENSHOTS_DIR / "02_session_report_modal.png")
    img_history = _encode_png_b64(SCREENSHOTS_DIR / "04_assets_history.png")

    phys_webcam = SCREENSHOTS_DIR / "07_physical_webcam_valid.png"
    has_physical = phys_webcam.is_file()
    if has_physical:
        fig6_html = f"""
        <div class="fig-card">
          <div class="shot-frame">
            <img src="{_encode_png_b64(phys_webcam)}" alt="Physical FaceTime HD Webcam Tracking" style="max-height: 62mm; width: auto; margin: 0 auto;" />
          </div>
          <div class="fig-caption">
            <strong>Figure 7:</strong> Live Physical MacBook FaceTime HD Camera tracking mobile dark-ground <code>/target</code> optical bench pattern (<code>30.3 Hz</code>, <code>STABLE</code>, <code>2.04%</code> jitter, <code>0</code> drops, Y-axis <code>4.00 Hz VALID</code> at <code>38.3 dB</code>, <code>TGT/ANC CORR 0.99/1.00</code>, <code>&sigma;=70.3/77.9</code>).
          </div>
        </div>
        """
    else:
        img_cam = _encode_png_b64(SCREENSHOTS_DIR / "00_webcam_live_active.png")
        img_target = _encode_png_b64(SCREENSHOTS_DIR / "05_optical_target.png")
        fig6_html = f"""
        <div class="fig-card">
          <div class="grid-2" style="gap: 8px;">
            <div class="shot-frame">
              <img src="{img_cam}" alt="Browser getUserMedia Active Stream" style="max-height: 55mm;" />
            </div>
            <div class="shot-frame">
              <img src="{img_target}" alt="Optical Bench Test Target" style="max-height: 55mm;" />
            </div>
          </div>
          <div class="fig-caption">
            <strong>Figure 7:</strong> Left — Live browser <code>getUserMedia</code> textured camera binary ingest (<code>60.8 Hz</code>, <code>0</code> dropped frames, <code>8.51 Hz</code> peak). Right — Built-in <code>/target</code> dark-ground anti-overexposure 720p calibration target (16–38 px matte blocks, <code>σ &gt; 40</code>).
          </div>
        </div>
        """

    # Inline Vector SVG Figure 1: End-to-End Continuous Pipeline
    svg_fig1 = """
    <svg viewBox="0 0 760 112" width="100%" xmlns="http://www.w3.org/2000/svg" style="display:block;">
      <defs>
        <marker id="arr1" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 8 5 L 0 9 z" fill="#0891B2"/>
        </marker>
      </defs>
      <!-- Nodes -->
      <rect x="4" y="16" width="112" height="72" rx="6" fill="#F8FAFC" stroke="#CBD5E1" stroke-width="1.2"/>
      <text x="60" y="36" text-anchor="middle" font-size="8.5" font-weight="700" fill="#0E7490">ACQUISITION</text>
      <text x="60" y="51" text-anchor="middle" font-size="8" fill="#0F172A">Browser Camera</text>
      <text x="60" y="63" text-anchor="middle" font-size="8" fill="#0F172A">getUserMedia /</text>
      <text x="60" y="75" text-anchor="middle" font-size="8" fill="#334155">500 FPS Replay</text>

      <line x1="116" y1="52" x2="132" y2="52" stroke="#0891B2" stroke-width="1.5" marker-end="url(#arr1)"/>

      <rect x="134" y="16" width="114" height="72" rx="6" fill="#F0F9FF" stroke="#0891B2" stroke-width="1.2"/>
      <text x="191" y="36" text-anchor="middle" font-size="8.5" font-weight="700" fill="#0E7490">BINARY INGEST</text>
      <text x="191" y="51" text-anchor="middle" font-size="8" fill="#0F172A">Lossless ROI</text>
      <text x="191" y="63" text-anchor="middle" font-size="8" fill="#0F172A">Patch Stream</text>
      <text x="191" y="75" text-anchor="middle" font-size="7.5" font-family="monospace" fill="#334155">&lt;dIHHHHI (~18 KB)</text>

      <line x1="248" y1="52" x2="264" y2="52" stroke="#0891B2" stroke-width="1.5" marker-end="url(#arr1)"/>

      <rect x="266" y="16" width="116" height="72" rx="6" fill="#F8FAFC" stroke="#CBD5E1" stroke-width="1.2"/>
      <text x="324" y="36" text-anchor="middle" font-size="8.5" font-weight="700" fill="#0E7490">OPTICAL CORE</text>
      <text x="324" y="51" text-anchor="middle" font-size="8" fill="#0F172A">Sub-Pixel Phase</text>
      <text x="324" y="63" text-anchor="middle" font-size="8" fill="#0F172A">Correlation &amp;</text>
      <text x="324" y="75" text-anchor="middle" font-size="8" fill="#334155">Anchor Subtract</text>

      <line x1="382" y1="52" x2="398" y2="52" stroke="#0891B2" stroke-width="1.5" marker-end="url(#arr1)"/>

      <rect x="400" y="16" width="114" height="72" rx="6" fill="#F8FAFC" stroke="#CBD5E1" stroke-width="1.2"/>
      <text x="457" y="36" text-anchor="middle" font-size="8.5" font-weight="700" fill="#0E7490">SPECTRAL ENGINE</text>
      <text x="457" y="51" text-anchor="middle" font-size="8" fill="#0F172A">Ring Buffer +</text>
      <text x="457" y="63" text-anchor="middle" font-size="8" fill="#0F172A">Rolling Welch PSD</text>
      <text x="457" y="75" text-anchor="middle" font-size="7.5" fill="#334155">(192 / 384 / 512)</text>

      <line x1="514" y1="52" x2="530" y2="52" stroke="#0891B2" stroke-width="1.5" marker-end="url(#arr1)"/>

      <rect x="532" y="16" width="112" height="72" rx="6" fill="#FFFBEB" stroke="#D97706" stroke-width="1.2"/>
      <text x="588" y="36" text-anchor="middle" font-size="8.5" font-weight="700" fill="#B45309">SCREENING GATE</text>
      <text x="588" y="51" text-anchor="middle" font-size="8" fill="#0F172A">Confidence Gate</text>
      <text x="588" y="63" text-anchor="middle" font-size="8" fill="#0F172A">+ Median / MAD</text>
      <text x="588" y="75" text-anchor="middle" font-size="8" fill="#334155">Baseline (Z ≥ 3.0)</text>

      <line x1="644" y1="52" x2="660" y2="52" stroke="#0891B2" stroke-width="1.5" marker-end="url(#arr1)"/>

      <rect x="662" y="16" width="94" height="72" rx="6" fill="#F0FDF4" stroke="#059669" stroke-width="1.2"/>
      <text x="709" y="36" text-anchor="middle" font-size="8.5" font-weight="700" fill="#047857">OUTPUT</text>
      <text x="709" y="51" text-anchor="middle" font-size="8" fill="#0F172A">Live UI Scope</text>
      <text x="709" y="63" text-anchor="middle" font-size="8" fill="#0F172A">+ JSON Report</text>
      <text x="709" y="75" text-anchor="middle" font-size="8" fill="#334155">SQLite WAL / NPZ</text>
    </svg>
    """

    # Inline Vector SVG Figure 2: 4-Layer Architecture
    svg_fig2 = """
    <svg viewBox="0 0 760 194" width="100%" xmlns="http://www.w3.org/2000/svg" style="display:block;">
      <defs>
        <marker id="arr2" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 8 5 L 0 9 z" fill="#0E7490"/>
        </marker>
      </defs>

      <!-- Layer 1: Next.js -->
      <rect x="6" y="8" width="166" height="178" rx="7" fill="#F0F9FF" stroke="#0891B2" stroke-width="1.3"/>
      <text x="89" y="26" text-anchor="middle" font-size="9" font-weight="800" fill="#0E7490">1. NEXT.JS WORKSTATION</text>
      <text x="89" y="38" text-anchor="middle" font-size="7.5" font-family="monospace" fill="#475569">frontend/ (Port 3000)</text>
      <rect x="16" y="48" width="146" height="28" rx="4" fill="#FFFFFF" stroke="#BAE6FD"/>
      <text x="89" y="65" text-anchor="middle" font-size="8" fill="#0F172A">ROI Canvas &amp; Live σ Check</text>
      <rect x="16" y="82" width="146" height="28" rx="4" fill="#FFFFFF" stroke="#BAE6FD"/>
      <text x="89" y="99" text-anchor="middle" font-size="8" fill="#0F172A">Oscilloscope &amp; Welch PSD SVG</text>
      <rect x="16" y="116" width="146" height="28" rx="4" fill="#FFFFFF" stroke="#BAE6FD"/>
      <text x="89" y="133" text-anchor="middle" font-size="8" fill="#0F172A">Webcam Binary Pump + /target</text>
      <rect x="16" y="150" width="146" height="26" rx="4" fill="#E0F2FE" stroke="#7DD3FC"/>
      <text x="89" y="166" text-anchor="middle" font-size="7.5" font-weight="600" fill="#0369A1">Batch &amp; History Overlay UI</text>

      <!-- Arrows L1 <-> L2 -->
      <line x1="172" y1="68" x2="196" y2="68" stroke="#0E7490" stroke-width="1.5" marker-end="url(#arr2)"/>
      <text x="185" y="61" text-anchor="middle" font-size="5.6" font-family="monospace" fill="#0E7490">/ingest</text>
      <line x1="196" y1="120" x2="172" y2="120" stroke="#0E7490" stroke-width="1.5" marker-end="url(#arr2)"/>
      <text x="185" y="113" text-anchor="middle" font-size="5.6" font-family="monospace" fill="#0E7490">REST/WS</text>

      <!-- Layer 2: FastAPI -->
      <rect x="198" y="8" width="166" height="178" rx="7" fill="#F8FAFC" stroke="#64748B" stroke-width="1.3"/>
      <text x="281" y="26" text-anchor="middle" font-size="9" font-weight="800" fill="#0F172A">2. FASTAPI SERVICE LAYER</text>
      <text x="281" y="38" text-anchor="middle" font-size="7.5" font-family="monospace" fill="#475569">backend/ (Port 8000)</text>
      <rect x="208" y="48" width="146" height="28" rx="4" fill="#FFFFFF" stroke="#CBD5E1"/>
      <text x="281" y="65" text-anchor="middle" font-size="8" fill="#0F172A">WS /ingest &amp; /telemetry</text>
      <rect x="208" y="82" width="146" height="28" rx="4" fill="#FFFFFF" stroke="#CBD5E1"/>
      <text x="281" y="99" text-anchor="middle" font-size="8" fill="#0F172A">REST /assets, /runs, /baselines</text>
      <rect x="208" y="116" width="146" height="28" rx="4" fill="#FFFFFF" stroke="#CBD5E1"/>
      <text x="281" y="133" text-anchor="middle" font-size="8" fill="#0F172A">MJPEG Replay /sessions/mjpeg</text>
      <rect x="208" y="150" width="146" height="26" rx="4" fill="#F1F5F9" stroke="#CBD5E1"/>
      <text x="281" y="166" text-anchor="middle" font-size="7.5" font-weight="600" fill="#334155">MonitoringManager Lifecycle</text>

      <!-- Arrows L2 <-> L3 -->
      <line x1="364" y1="95" x2="388" y2="95" stroke="#0E7490" stroke-width="1.5" marker-end="url(#arr2)"/>

      <!-- Layer 3: Monitoring Engine -->
      <rect x="390" y="8" width="174" height="178" rx="7" fill="#FFFBEB" stroke="#D97706" stroke-width="1.3"/>
      <text x="477" y="26" text-anchor="middle" font-size="9" font-weight="800" fill="#B45309">3. MONITORING ENGINE</text>
      <text x="477" y="38" text-anchor="middle" font-size="7.5" font-family="monospace" fill="#78350F">phasesight/monitoring/</text>
      <rect x="400" y="48" width="154" height="28" rx="4" fill="#FFFFFF" stroke="#FDE68A"/>
      <text x="477" y="65" text-anchor="middle" font-size="8" fill="#0F172A">Fixed-Mem Ring Buffer (512)</text>
      <rect x="400" y="82" width="154" height="28" rx="4" fill="#FFFFFF" stroke="#FDE68A"/>
      <text x="477" y="99" text-anchor="middle" font-size="8" fill="#0F172A">Adaptive Rolling Welch PSD</text>
      <rect x="400" y="116" width="154" height="28" rx="4" fill="#FFFFFF" stroke="#FDE68A"/>
      <text x="477" y="133" text-anchor="middle" font-size="8" fill="#0F172A">500 FPS Paced Video Adapter</text>
      <rect x="400" y="150" width="154" height="26" rx="4" fill="#FEF3C7" stroke="#F59E0B"/>
      <text x="477" y="166" text-anchor="middle" font-size="7.5" font-weight="600" fill="#92400E">Timing &amp; Warm-Up Gate FSM</text>

      <!-- Arrows L3 <-> L4 -->
      <line x1="564" y1="95" x2="588" y2="95" stroke="#0E7490" stroke-width="1.5" marker-end="url(#arr2)"/>

      <!-- Layer 4: Core + Persistence -->
      <rect x="590" y="8" width="164" height="178" rx="7" fill="#F0FDF4" stroke="#059669" stroke-width="1.3"/>
      <text x="672" y="26" text-anchor="middle" font-size="9" font-weight="800" fill="#047857">4. CORE &amp; PERSISTENCE</text>
      <text x="672" y="38" text-anchor="middle" font-size="7.5" font-family="monospace" fill="#065F46">phasesight/ &amp; data/storage/</text>
      <rect x="600" y="48" width="144" height="28" rx="4" fill="#FFFFFF" stroke="#A7F3D0"/>
      <text x="672" y="65" text-anchor="middle" font-size="8" fill="#0F172A">PhaseCorrelationTracker</text>
      <rect x="600" y="82" width="144" height="28" rx="4" fill="#FFFFFF" stroke="#A7F3D0"/>
      <text x="672" y="99" text-anchor="middle" font-size="8" fill="#0F172A">DEF-01 Spectral Analysis</text>
      <rect x="600" y="116" width="144" height="28" rx="4" fill="#FFFFFF" stroke="#A7F3D0"/>
      <text x="672" y="133" text-anchor="middle" font-size="8" fill="#0F172A">Median / Scaled-MAD Baseline</text>
      <rect x="600" y="150" width="144" height="26" rx="4" fill="#DCFCE7" stroke="#34D399"/>
      <text x="672" y="166" text-anchor="middle" font-size="7.5" font-weight="600" fill="#065F46">SQLite WAL + Compressed NPZ</text>
    </svg>
    """

    # Inline Vector SVG State Machine (Page 3)
    svg_fsm = """
    <svg viewBox="0 0 760 112" width="100%" xmlns="http://www.w3.org/2000/svg" style="display:block;">
      <defs>
        <marker id="arrFsm" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">
          <path d="M 0 1 L 8 5 L 0 9 z" fill="#475569"/>
        </marker>
        <marker id="arrErr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">
          <path d="M 0 1 L 8 5 L 0 9 z" fill="#E11D48"/>
        </marker>
      </defs>

      <rect x="4" y="16" width="76" height="36" rx="5" fill="#F1F5F9" stroke="#64748B" stroke-width="1.2"/>
      <text x="42" y="38" text-anchor="middle" font-size="8.5" font-weight="700" fill="#0F172A">CREATED</text>
      <line x1="80" y1="34" x2="100" y2="34" stroke="#475569" stroke-width="1.3" marker-end="url(#arrFsm)"/>

      <rect x="102" y="16" width="96" height="36" rx="5" fill="#F0F9FF" stroke="#0891B2" stroke-width="1.2"/>
      <text x="150" y="32" text-anchor="middle" font-size="8.5" font-weight="700" fill="#0E7490">CALIBRATING</text>
      <text x="150" y="44" text-anchor="middle" font-size="7" fill="#334155">t=0 ref, σ ≥ 2.0</text>
      <line x1="198" y1="34" x2="218" y2="34" stroke="#475569" stroke-width="1.3" marker-end="url(#arrFsm)"/>

      <rect x="220" y="16" width="98" height="36" rx="5" fill="#F8FAFC" stroke="#475569" stroke-width="1.2"/>
      <text x="269" y="32" text-anchor="middle" font-size="8.5" font-weight="700" fill="#0F172A">BUFFERING</text>
      <text x="269" y="44" text-anchor="middle" font-size="7" fill="#334155">n &lt; nperseg</text>
      <line x1="318" y1="34" x2="338" y2="34" stroke="#475569" stroke-width="1.3" marker-end="url(#arrFsm)"/>

      <rect x="340" y="16" width="110" height="36" rx="5" fill="#FFFBEB" stroke="#D97706" stroke-width="1.2"/>
      <text x="395" y="32" text-anchor="middle" font-size="8.5" font-weight="700" fill="#B45309">WARMING_UP</text>
      <text x="395" y="44" text-anchor="middle" font-size="7" fill="#78350F">nperseg ≤ n &lt; 2·nperseg</text>
      <line x1="450" y1="34" x2="472" y2="34" stroke="#475569" stroke-width="1.3" marker-end="url(#arrFsm)"/>

      <rect x="474" y="14" width="136" height="40" rx="5" fill="#F0FDF4" stroke="#059669" stroke-width="1.5"/>
      <text x="542" y="31" text-anchor="middle" font-size="9" font-weight="800" fill="#047857">ACTIVE</text>
      <text x="542" y="44" text-anchor="middle" font-size="7.5" fill="#065F46">Full Welch PSD + Baseline Z</text>
      <line x1="610" y1="34" x2="634" y2="34" stroke="#475569" stroke-width="1.3" marker-end="url(#arrFsm)"/>

      <rect x="636" y="16" width="118" height="36" rx="5" fill="#F1F5F9" stroke="#0F172A" stroke-width="1.2"/>
      <text x="695" y="32" text-anchor="middle" font-size="8.5" font-weight="700" fill="#0F172A">PERSISTED</text>
      <text x="695" y="44" text-anchor="middle" font-size="7" fill="#334155">SQLite WAL + NPZ Save</text>

      <!-- DEGRADED branch -->
      <path d="M 395 52 L 395 68 L 412 68" fill="none" stroke="#E11D48" stroke-width="1.2" marker-end="url(#arrErr)"/>
      <path d="M 520 54 L 520 68 L 512 68" fill="none" stroke="#E11D48" stroke-width="1.2"/>
      <rect x="360" y="68" width="218" height="36" rx="5" fill="#FFF1F2" stroke="#E11D48" stroke-width="1.2"/>
      <text x="469" y="84" text-anchor="middle" font-size="8.5" font-weight="700" fill="#BE123C">DEGRADED (Trust Withheld)</text>
      <text x="469" y="96" text-anchor="middle" font-size="7" fill="#881337">gap &gt; 2.5×dt, drop &gt; 8%, or valid &lt; 85%</text>
      <path d="M 360 86 L 269 86 L 269 54" fill="none" stroke="#64748B" stroke-width="1.1" stroke-dasharray="3,2" marker-end="url(#arrFsm)"/>
      <text x="315" y="81" text-anchor="middle" font-size="6.8" fill="#475569">Buffer Reset / Re-lock</text>
    </svg>
    """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>PhaseSight — PRASUNEX Innovathon 2026 Round 3 Submission</title>
<style>
  @page {{
    size: A4;
    margin: 13mm 14mm 15mm 14mm;
  }}
  * {{
    box-sizing: border-box;
  }}
  html, body {{
    margin: 0;
    padding: 0;
    background: #FFFFFF;
    color: #0F172A;
    font-family: "SF Pro Text", "Helvetica Neue", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 9.2pt;
    line-height: 1.42;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  .page {{
    page-break-after: always;
    break-after: page;
  }}
  .page:last-child {{
    page-break-after: auto;
    break-after: auto;
  }}
  code, .mono {{
    font-family: "SF Mono", "IBM Plex Mono", Menlo, Monaco, Consolas, monospace;
    font-variant-numeric: tabular-nums;
  }}
  code {{
    background: #F1F5F9;
    color: #0E7490;
    padding: 0.5px 3.5px;
    border-radius: 3px;
    font-size: 8.2pt;
  }}
  .tabular {{
    font-variant-numeric: tabular-nums;
  }}

  /* Cover & Section Headings */
  .top-bar {{
    background: #0F172A;
    color: #F8FAFC;
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 0.08em;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }}
  .top-bar span.accent {{
    color: #22D3EE;
  }}
  h1.cover-title {{
    font-size: 18pt;
    line-height: 1.18;
    font-weight: 800;
    color: #0F172A;
    margin: 0 0 8px 0;
    letter-spacing: -0.015em;
  }}
  .meta-strip {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px 14px;
    padding: 6px 10px;
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 4px;
    font-size: 8.2pt;
    color: #334155;
    margin-bottom: 10px;
  }}
  .meta-strip strong {{
    color: #0F172A;
  }}

  .links-card {{
    background: #F0F9FF;
    border: 1.5px solid #0891B2;
    border-radius: 6px;
    padding: 9px 12px;
    margin-bottom: 11px;
  }}
  .links-card .links-title {{
    font-size: 8.5pt;
    font-weight: 800;
    color: #0E7490;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-bottom: 5px;
  }}
  .links-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }}
  .link-item {{
    background: #FFFFFF;
    border: 1px solid #BAE6FD;
    border-radius: 4px;
    padding: 6px 9px;
  }}
  .link-label {{
    font-size: 7.5pt;
    font-weight: 700;
    color: #475569;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    display: block;
    margin-bottom: 2px;
  }}
  .link-item a {{
    font-family: "SF Mono", Menlo, monospace;
    font-size: 8.2pt;
    color: #0E7490;
    font-weight: 600;
    text-decoration: underline;
    word-break: break-all;
  }}
  .link-sub {{
    font-size: 7.4pt;
    color: #475569;
    display: block;
    margin-top: 2px;
  }}

  .sec-eyebrow {{
    font-size: 11.5pt;
    font-weight: 800;
    color: #0E7490;
    border-bottom: 2px solid #0E7490;
    padding-bottom: 3px;
    margin: 0 0 9px 0;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }}
  h2.sub-head {{
    font-size: 9.8pt;
    font-weight: 700;
    color: #0F172A;
    margin: 10px 0 5px 0;
  }}
  p {{
    margin: 0 0 7px 0;
    color: #334155;
  }}
  ul {{
    margin: 4px 0 7px 0;
    padding-left: 16px;
    color: #334155;
  }}
  li {{
    margin-bottom: 3px;
  }}

  /* Cards & Grids */
  .grid-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }}
  .card {{
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 5px;
    padding: 8px 10px;
    break-inside: avoid;
  }}
  .card-cyan {{
    background: #F0F9FF;
    border: 1px solid #BAE6FD;
    border-left: 3.5px solid #0891B2;
  }}
  .card-amber {{
    background: #FFFBEB;
    border: 1px solid #FDE68A;
    border-left: 3.5px solid #D97706;
  }}
  .card-emerald {{
    background: #F0FDF4;
    border: 1px solid #BBF7D0;
    border-left: 3.5px solid #059669;
  }}
  .card-title {{
    font-size: 8.5pt;
    font-weight: 800;
    color: #0F172A;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }}

  /* Formula Boxes */
  .formula-box {{
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-left: 3.5px solid #0E7490;
    border-radius: 4px;
    padding: 7px 10px;
    break-inside: avoid;
  }}
  .formula-title {{
    font-size: 8.4pt;
    font-weight: 700;
    color: #0E7490;
    margin-bottom: 3px;
  }}
  .formula-math {{
    font-family: "SF Mono", Menlo, monospace;
    font-size: 8pt;
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 3px;
    padding: 4px 7px;
    color: #0F172A;
    margin: 3px 0 4px 0;
  }}
  .formula-desc {{
    font-size: 7.9pt;
    color: #475569;
    margin: 0;
  }}

  /* Tables */
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 5px 0 9px 0;
    font-size: 8pt;
    font-variant-numeric: tabular-nums;
    break-inside: avoid;
  }}
  th {{
    background: #F1F5F9;
    color: #0F172A;
    font-weight: 700;
    text-align: left;
    padding: 5px 7px;
    border-top: 1.5px solid #0F172A;
    border-bottom: 1.2px solid #94A3B8;
  }}
  td {{
    padding: 4.5px 7px;
    border-bottom: 1px solid #E2E8F0;
    color: #334155;
    vertical-align: top;
  }}
  tr:nth-child(even) td {{
    background: #FAFBFD;
  }}
  .badge {{
    display: inline-block;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 7.2pt;
    font-weight: 700;
    font-family: "SF Mono", Menlo, monospace;
  }}
  .badge-pass {{ background: #DCFCE7; color: #166534; border: 1px solid #86EFAC; }}
  .badge-warn {{ background: #FEF3C7; color: #92400E; border: 1px solid #FCD34D; }}
  .badge-contam {{ background: #FFE4E6; color: #9F1239; border: 1px solid #FDA4AF; }}

  /* Figures & Screenshots */
  .diagram-box {{
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 7px 8px 5px 8px;
    margin: 6px 0 9px 0;
    break-inside: avoid;
  }}
  .fig-card {{
    margin-bottom: 8px;
    break-inside: avoid;
  }}
  .shot-frame {{
    background: #070A0F;
    border: 1px solid #1E293B;
    border-radius: 5px;
    padding: 3px;
    text-align: center;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.12);
  }}
  .shot-frame img {{
    display: block;
    width: 100%;
    height: auto;
    object-fit: contain;
    border-radius: 3px;
  }}
  .fig-caption {{
    font-size: 7.9pt;
    color: #475569;
    margin-top: 3px;
    line-height: 1.3;
  }}
  .fig-caption strong {{
    color: #0F172A;
  }}

  .ref-list {{
    font-size: 7.6pt;
    color: #475569;
    padding-left: 14px;
    margin: 4px 0 0 0;
  }}
  .ref-list li {{
    margin-bottom: 2px;
  }}
</style>
</head>
<body>

<!-- ====================================================================== -->
<!-- PAGE 1: EXECUTIVE COVER & PROTOTYPE OVERVIEW                           -->
<!-- ====================================================================== -->
<section class="page">
  <div class="top-bar">
    <span>PRASUNEX INNOVATHON 2026 <span class="accent">|</span> ROUND 3 — PROTOTYPE DEVELOPMENT &amp; DEMONSTRATION</span>
    <span class="accent">NOV 25, 2026</span>
  </div>

  <h1 class="cover-title">
    PHASESIGHT — Continuous Non-Contact Camera-Based Machine Vibration Screening Workstation
  </h1>

  <div class="meta-strip">
    <span><strong>Applicant:</strong> Kartikey Gupta (Solo)</span>
    <span><strong>Stack:</strong> Next.js 16 · FastAPI · OpenCV · SciPy · SQLite/NPZ</span>
    <span><strong>Verification:</strong> <span class="tabular">137/137</span> Pytest · <span class="tabular">6/6</span> T1–T6 · <span class="tabular">0</span> Browser Errors</span>
  </div>

  <div class="links-card">
    <div class="links-title">Submission Artifacts &amp; Demonstration Links</div>
    <div class="links-grid">
      <div class="link-item">
        <span class="link-label">Live Prototype Demo Video (Unlisted YouTube)</span>
        <a href="{safe_video}">{safe_video}</a>
        <span class="link-sub">Live webcam binary ingest, 500 FPS replay, baseline calibration &amp; Review screening.</span>
      </div>
      <div class="link-item">
        <span class="link-label">Source Code Repository (GitHub)</span>
        <a href="{safe_repo}">{safe_repo}</a>
        <span class="link-sub">Local-first full-stack execution via <code>./scripts/dev.sh</code> (no cloud lock-in).</span>
      </div>
    </div>
  </div>

  <h2 class="sub-head">Executive Problem Statement &amp; Solution</h2>
  <p>
    Industrial rotating assets (pumps, fans, blowers, rotor housings) routinely suffer delayed condition monitoring when wired accelerometers or proximity probes cannot be installed due to high temperature, rotating surfaces, inaccessible enclosures, or sensor mass-loading. PhaseSight turns fixed commodity or high-speed cameras into non-contact sub-pixel optical vibration screening instruments without mounting hardware on the asset.
  </p>
  <p>
    Using normalized Fourier phase correlation (<code>cv2.phaseCorrelate</code>) differential to a rigid stationary background anchor, PhaseSight isolates structural target motion from tripod shake—recovering synthetic 8.5 Hz vibration at <strong>0.009 Hz</strong> frequency error and <strong>0.051 px</strong> displacement RMSE (<em>r</em> = 0.976)—then screens rolling Welch PSD spectra against robust N&ge;3 Median/Scaled-MAD asset baselines (<em>Z</em><sub>robust</sub> &gt; 3.0).
  </p>

  <div class="diagram-box">
    {svg_fig1}
    <div class="fig-caption">
      <strong>Figure 1:</strong> End-to-end continuous optical monitoring pipeline from browser <code>getUserMedia</code> or paced 500 FPS video replay through binary ROI ingest, anchor subtraction, rolling Welch PSD, statistical screening, and ACID persistence.
    </div>
  </div>

  <div class="grid-2">
    <div class="card">
      <div class="card-title">Round 2 Proposal Scope</div>
      <ul>
        <li>Finite offline MP4 clip inspection workflow &amp; synchronous prototype batch scripts.</li>
        <li>Manual static Streamlit file upload UI without real-time streaming telemetry or live scope.</li>
        <li>Global-peak-only anchor contamination check without secondary harmonic scanning.</li>
      </ul>
    </div>
    <div class="card card-emerald">
      <div class="card-title">Round 3 Delivered Workstation (Exceeded)</div>
      <ul>
        <li><strong>Continuous Engine:</strong> Real-time circular ring buffers, adaptive Welch PSD &amp; FSM timing gates.</li>
        <li><strong>Precision Web UI:</strong> Next.js 16 + FastAPI WebSocket workstation, live Canvas oscilloscope &amp; <code>/target</code>.</li>
        <li><strong>Hardened Math:</strong> DEF-01 secondary-peak check (&ge;10 dB) &amp; live 3-run Median/MAD deviation alerting.</li>
      </ul>
    </div>
  </div>
</section>

<!-- ====================================================================== -->
<!-- PAGE 2: 01 / SYSTEM ARCHITECTURE & CONTINUOUS ENGINE                   -->
<!-- ====================================================================== -->
<section class="page">
  <div class="sec-eyebrow">01 / System Architecture &amp; Continuous Engine</div>
  <p>
    To decouple latency-sensitive client visualization from deterministic NumPy/SciPy numerical processing, PhaseSight uses a strictly stratified 4-layer architecture where the scientific core remains 100% framework-independent and shared between offline batch inspection and continuous live streaming.
  </p>

  <div class="diagram-box">
    {svg_fig2}
    <div class="fig-caption">
      <strong>Figure 2:</strong> Decoupled 4-layer system architecture connecting the browser workstation (<code>frontend/</code>), REST &amp; binary WebSocket layer (<code>backend/</code>), rolling acquisition engine (<code>phasesight/monitoring/</code>), and SQLite WAL / NPZ persistence.
    </div>
  </div>

  <h2 class="sub-head">Key Architectural &amp; Systems Engineering Decisions</h2>
  <table>
    <thead>
      <tr>
        <th style="width: 24%;">Design Choice</th>
        <th style="width: 44%;">Engineering Rationale</th>
        <th style="width: 32%;">Measured Impact</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>Binary ROI Patch Ingest</strong><br/><code>&lt;dIHHHHI</code></td>
        <td>Crops Target &amp; Anchor patches locally via single Canvas <code>drawImage</code> readback instead of streaming full-frame JPEG/H.264 video.</td>
        <td>~18 KB/frame vs ~2 MB full-frame RGB (&gt;98% bandwidth cut) with zero compression blocking artifacts.</td>
      </tr>
      <tr>
        <td><strong>Fixed <em>t</em>=0 Reference + Manual Re-lock</strong></td>
        <td>Correlates against locked initial patches rather than frame-to-frame sequential chaining, preventing random-walk drift accumulation.</td>
        <td>Eliminates &radic;<em>t</em> Brownian baseline drift over long runs while supporting explicit <code>Re-lock Reference</code> resets.</td>
      </tr>
      <tr>
        <td><strong>Adaptive Rolling Welch Window</strong></td>
        <td>Slices active ring buffer to <code>min(cap, 3·nperseg)</code> (192 samples @ 30 FPS, 384 @ 60 FPS, 512 @ 500 FPS) for online spectral estimates.</td>
        <td>Enables 5 overlapping Welch segments in ~6.4 s @ 30 FPS while preserving 512-sample parity @ 500 FPS.</td>
      </tr>
      <tr>
        <td><strong>Local-First Edge Stack</strong></td>
        <td>Runs FastAPI, Next.js, SQLite WAL, and compressed NPZ archives locally on standard macOS/Linux without cloud dependencies.</td>
        <td>Deterministic zero-egress industrial privacy; single-command startup via <code>./scripts/dev.sh</code>.</td>
      </tr>
    </tbody>
  </table>

  <h2 class="sub-head">Repository Package &amp; Module Inventory</h2>
  <table>
    <thead>
      <tr>
        <th style="width: 24%;">Layer / Directory</th>
        <th style="width: 48%;">Primary Modules &amp; Responsibilities</th>
        <th style="width: 28%;">Key Interfaces</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><code>phasesight/</code><br/>Scientific Core</td>
        <td><code>tracker.py</code> (FFT phase correlation), <code>analysis.py</code> (Welch PSD, DEF-01 check), <code>baseline.py</code> (Median/MAD Z-scoring), <code>capture.py</code>, <code>storage.py</code> (SQLite WAL + NPZ).</td>
        <td><code>PhaseCorrelationTracker</code>, <code>analyse_displacement()</code>, <code>StorageManager</code></td>
      </tr>
      <tr>
        <td><code>phasesight/monitoring/</code><br/>Continuous Engine</td>
        <td><code>ring_buffer.py</code> (thread-safe pre-allocated circular arrays), <code>rolling_analysis.py</code> (FSM &amp; timing gates), <code>session.py</code>, <code>replay_adapter.py</code> (500 FPS pacing).</td>
        <td><code>MonitoringSession</code>, <code>analyze_rolling_window()</code>, <code>PacedVideoReplayAdapter</code></td>
      </tr>
      <tr>
        <td><code>backend/</code><br/>FastAPI Service</td>
        <td><code>main.py</code>, <code>manager.py</code>, <code>ws.py</code> (<code>/ingest</code>, <code>/telemetry</code>), <code>routes/{{assets,videos,runs,baselines,sessions,health}}.py</code>, <code>presets.py</code>.</td>
        <td>REST <code>/api/v1/*</code>, Binary &amp; JSON WebSockets, MJPEG stream</td>
      </tr>
      <tr>
        <td><code>frontend/</code><br/>Next.js 16 Workstation</td>
        <td><code>LiveMonitorView</code>, <code>BatchInspectView</code>, <code>AssetsHistoryView</code>, <code>RoiInteractiveCanvas</code>, <code>OscilloscopeCanvas</code>, <code>SpectrumPlot</code>, <code>/target</code> calibrator.</td>
        <td>App Router UI (port 3000), <code>WebcamStreamer</code>, JSON Report Export</td>
      </tr>
    </tbody>
  </table>
</section>

<!-- ====================================================================== -->
<!-- PAGE 3: 02 / SIGNAL MATHEMATICS & QUALITY GATES                        -->
<!-- ====================================================================== -->
<section class="page">
  <div class="sec-eyebrow">02 / Signal Mathematics &amp; Quality Gates</div>
  <p>
    Every optical estimate passes through explicit texture, correlation, temporal stability, and common-mode contamination gates. Rather than fabricating fault predictions over degraded video, PhaseSight withdraws trust deterministically whenever physical assumptions break down.
  </p>

  <div class="grid-2" style="margin-bottom: 10px;">
    <div class="formula-box">
      <div class="formula-title">1. Sub-Pixel Phase Correlation &amp; Anchor Subtraction</div>
      <div class="formula-math">
        R(u,v) = F{{I<sub>t</sub>}}·F{{I<sub>0</sub>}}* / |F{{I<sub>t</sub>}}·F{{I<sub>0</sub>}}*|<br/>
        <strong>d</strong><sub>rel</sub>(t) = <strong>d</strong><sub>target</sub>(t) &minus; <strong>d</strong><sub>anchor</sub>(t)
      </div>
      <p class="formula-desc">
        Hann-windowed patches are correlated in Fourier space with 2D parabolic sub-pixel peak interpolation (<code>min_texture_std = 2.0</code>, <code>min_response = 0.15</code>). Subtracting rigid anchor displacement cancels camera shake.
      </p>
    </div>

    <div class="formula-box">
      <div class="formula-title">2. Median Welch PSD &amp; Log-Parabolic Peak Localization</div>
      <div class="formula-math">
        P<sub>xx</sub>(f) = Welch<sub>median</sub>(detrend(<strong>d</strong><sub>rel</sub>), nperseg)<br/>
        &delta; = 0.5·(L<sub>&minus;1</sub> &minus; L<sub>+1</sub>) / (L<sub>&minus;1</sub> &minus; 2L<sub>0</sub> + L<sub>+1</sub>)
      </div>
      <p class="formula-desc">
        Linearly detrended segments use Hann windows (50% overlap, median averaging) across <code>0.5 Hz &le; f &le; 0.90·f<sub>Nyq</sub></code>. Three-point parabolic interpolation over log-PSD <code>L = ln(P<sub>xx</sub>)</code> achieves sub-bin frequency precision.
      </p>
    </div>

    <div class="formula-box">
      <div class="formula-title">3. DEF-01 Multi-Peak Anchor Contamination Guard</div>
      <div class="formula-math">
        P<sub>prom</sub>(f<sub>cand</sub>) = 10·log<sub>10</sub>(P<sub>anc</sub>[f<sub>cand</sub>] / med(P<sub>anc,bg</sub>)) &ge; 10.0 dB<br/>
        |f<sub>cand</sub> &minus; f<sub>rel,dom</sub>| &le; tol
      </div>
      <p class="formula-desc">
        Audits both the anchor global peak and any interior local anchor peak within frequency resolution tolerance <code>tol</code>. If anchor prominence reaches <strong>&ge; 10.0 dB</strong> at the target peak, the axis is flagged <code>CONTAMINATED</code>.
      </p>
    </div>

    <div class="formula-box">
      <div class="formula-title">4. Two-Stage Statistical Screening (Median / Scaled-MAD)</div>
      <div class="formula-math">
        MAD<sub>scaled</sub> = 1.4826 · median(|X &minus; median(X)|)<br/>
        Z<sub>robust</sub> = (x<sub>curr</sub> &minus; median<sub>base</sub>) / (MAD<sub>scaled</sub> + &epsilon;)
      </div>
      <p class="formula-desc">
        Built from &ge;3 valid calibration runs across Dominant Frequency, RMS Displacement, Peak Prominence (dB), and 2X Harmonic Ratio. Stage 1 validates sample/ROI/FPS confidence; Stage 2 flags <code>Review</code> if any |<em>Z</em><sub>robust</sub>| &gt; 3.0.
      </p>
    </div>
  </div>

  <h2 class="sub-head">Continuous Monitoring Finite State Machine &amp; Live Timing Resilience</h2>
  <div class="diagram-box">
    {svg_fsm}
    <div class="fig-caption">
      <strong>Figure 3 (FSM):</strong> Honesty-first state machine preventing premature spectral readouts during Welch warm-up and forcing buffer reset on severe burst stalls or tracking loss.
    </div>
  </div>

  <div class="grid-2">
    <div class="card card-cyan">
      <div class="card-title">Live Stream Timing Gate (<code>rolling_analysis.py</code>)</div>
      <ul>
        <li><strong>STABLE:</strong> Strictly monotonic timestamps, 0 drops, jitter &lt; 5%.</li>
        <li><strong>WARNING_JITTER:</strong> Isolated browser skips (0 large gaps &gt; 2.5&times;<em>dt</em>, drop fraction &le; 8%, jitter &lt; 22%) resampled cleanly onto a uniform time grid.</li>
        <li><strong>REJECTED_UNSTABLE / DEGRADED:</strong> Burst stall &gt; 2.5&times;<em>dt</em>, drop fraction &gt; 8%, or non-monotonic timestamps reset buffer and withhold PSD.</li>
      </ul>
    </div>
    <div class="card card-amber">
      <div class="card-title">Optical Quality &amp; Integrity Gates</div>
      <ul>
        <li><strong>Texture Pre-Flight:</strong> ROI grayscale &sigma; &lt; 2.0 rejects blank walls or out-of-focus regions before session initialization.</li>
        <li><strong>Correlation Gate:</strong> Mean normalized phase correlation response &lt; 0.15 invalidates frames; &lt;85% valid ratio halts analysis in <code>DEGRADED</code>.</li>
        <li><strong>Timebase Provenance:</strong> Explicit separation of measured clock vs <code>explicit_fps_override</code> (<code>ASSUMED_UNIFORM</code>) container overrides.</li>
      </ul>
    </div>
  </div>
</section>

<!-- ====================================================================== -->
<!-- PAGE 4: 03 / WORKING PROTOTYPE SHOWCASE (LIVE SCREENSHOTS)             -->
<!-- ====================================================================== -->
<section class="page">
  <div class="sec-eyebrow">03 / Working Prototype Showcase (Verified Live UI)</div>
  <p style="margin-bottom: 6px;">
    Unedited Playwright Chromium captures from the running Next.js + FastAPI Precision Workstation demonstrating live high-speed replay, real-time baseline <code>Review</code> deviation alerting, common-mode anchor cancellation, and historical multi-run spectral overlays.
  </p>

  <div class="grid-2" style="margin-bottom: 6px;">
    <div class="fig-card" style="margin-bottom: 2px;">
      <div class="shot-frame">
        <img src="{img_live_500}" alt="500 FPS Mendeley Rotor Live Replay" style="max-height: 74mm;" />
      </div>
      <div class="fig-caption">
        <strong>Figure 4 — Live 500 FPS Rotor Replay:</strong> <code>rotor_1000rpm_unb1</code> active at <code>500.0 Hz</code> (<code>ASSUMED UNIFORM</code>). Recovers X-axis 1X fundamental at <strong>16.53 Hz</strong> (0.1028 px) &amp; Y-axis 2X at <strong>33.40 Hz</strong> (0.0773 px), both <code>VALID</code> with observed <code>TGT CORR 1.00</code> / <code>ANC CORR 1.00</code>.
      </div>
    </div>

    <div class="fig-card" style="margin-bottom: 2px;">
      <div class="shot-frame">
        <img src="{img_review}" alt="Live Baseline REVIEW Screening" style="max-height: 74mm;" />
      </div>
      <div class="fig-caption">
        <strong>Figure 5 — Live Baseline Screening (<code>REVIEW</code>):</strong> Evaluating altered vibration on active asset triggers pulsing <code>REVIEW</code> badge (<strong>Max |z| = 22.44</strong>), emerald <code>BASELINE 8.51 Hz</code> PSD reference marker, and live <code>Raw Shake</code> RMS cancellation pill.
      </div>
    </div>
  </div>

  <div class="fig-card" style="margin-bottom: 0;">
    <div class="grid-2">
      <div class="shot-frame">
        <img src="{img_report}" alt="Session Report Modal" style="max-height: 74mm;" />
      </div>
      <div class="shot-frame">
        <img src="{img_history}" alt="Assets and History Multi-Run PSD Overlay" style="max-height: 74mm;" />
      </div>
    </div>
    <div class="fig-caption">
      <strong>Figure 6 — Session Persistence &amp; Multi-Run Overlay Inspector:</strong> Left — Immutable Session Report modal displaying exact <code>explicit_fps_override</code> provenance, <code>Jitter: N/A (Synthesized)</code> disclosure, and one-click <code>Export Report JSON</code>. Right — Assets &amp; History Run Inspector overlaying a reference spectrum (dashed emerald trace) atop an inspected run on unified dB axes.
    </div>
  </div>
</section>

<!-- ====================================================================== -->
<!-- PAGE 5: 04 / VERIFICATION, BENCHMARKS & HARDWARE VALIDATION            -->
<!-- ====================================================================== -->
<section class="page">
  <div class="sec-eyebrow">04 / Verification, Benchmarks &amp; Hardware Validation</div>

  <h2 class="sub-head" style="margin-top: 2px;">Synthetic Validation Matrix (<code>phasesight/validation.py</code> Protocols T1–T6)</h2>
  <table>
    <thead>
      <tr>
        <th style="width: 19%;">Protocol</th>
        <th style="width: 31%;">Synthetic Stimulus</th>
        <th style="width: 24%;">Acceptance Criteria</th>
        <th style="width: 18%;">Observed Result</th>
        <th style="width: 8%;">Verdict</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>T1: Motion Recovery</strong></td>
        <td>8.5 Hz (0.35 px) + 17.0 Hz 2X harmonic</td>
        <td>&Delta;f &le; 0.05 Hz, RMSE &le; 0.10 px, r &ge; 0.90</td>
        <td>&Delta;f = 0.009 Hz, RMSE = 0.051 px, r = 0.976</td>
        <td><span class="badge badge-pass">PASS</span></td>
      </tr>
      <tr>
        <td><strong>T2: Negative Control</strong></td>
        <td>Static (&sigma;=1.0) &amp; pure camera shake (0.65 px)</td>
        <td>RMS &le; 0.08 px, Prom &lt; 10 dB, <code>LOW_SIGNAL</code></td>
        <td>RMS = 0.021 px, Prom = 2.1 dB, <code>LOW_SIGNAL</code></td>
        <td><span class="badge badge-pass">PASS</span></td>
      </tr>
      <tr>
        <td><strong>T3: Camera Shake</strong></td>
        <td>8.5 Hz target (0.35 px) + 0.7 Hz shake (0.65 px)</td>
        <td>Supp &ge; 10 dB, Err red &ge; 60%, r &ge; 0.90</td>
        <td>Supp = 12.5 dB, Red = 76.4%, r = 0.963</td>
        <td><span class="badge badge-pass">PASS</span></td>
      </tr>
      <tr>
        <td><strong>T4: Repeatability</strong></td>
        <td>3 baseline runs (seeds 101, 102, 103)</td>
        <td>MAD<sub>f</sub> &lt; 0.01 Hz, MAD<sub>RMS</sub> &lt; 0.01 px</td>
        <td>MAD<sub>f</sub> = 0.000 Hz, MAD<sub>RMS</sub> = 0.002 px</td>
        <td><span class="badge badge-pass">PASS</span></td>
      </tr>
      <tr>
        <td><strong>T5: Change Alert</strong></td>
        <td>Baseline (0.23 px) vs Changed (0.35 px + 2X)</td>
        <td>Status <code>Review</code>, Z<sub>RMS</sub> &ge; 3.0</td>
        <td>Status <code>Review</code>, Z<sub>RMS</sub> = +22.54, Z<sub>2X</sub> = +5.72</td>
        <td><span class="badge badge-pass">PASS</span></td>
      </tr>
      <tr>
        <td><strong>T6: Quality Stress</strong></td>
        <td>Flat (&sigma;=0), blur, flicker, 400 ms stall</td>
        <td>All 4 gates trigger explicit rejection</td>
        <td>Texture, <code>LOW_SIGNAL</code>, <code>CONTAM</code>, <code>REJECTED</code></td>
        <td><span class="badge badge-pass">PASS</span></td>
      </tr>
    </tbody>
  </table>

  <h2 class="sub-head">Public Industrial Benchmark: Mendeley SpectraQuest Rotor Rig (500 FPS, DOI: <code>10.17632/47y7rwc2yg.1</code>)</h2>
  <table>
    <thead>
      <tr>
        <th style="width: 22%;">Test Case (500 FPS Overridden)</th>
        <th style="width: 18%;">Theoretical 1X</th>
        <th style="width: 24%;">X-Axis Output (Target C)</th>
        <th style="width: 24%;">Y-Axis Output (Target C)</th>
        <th style="width: 12%;">Quality Gate</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>1000 RPM Unbalance</strong><br/><code>1000rpm-Unb1.avi</code></td>
        <td>16.67 Hz</td>
        <td>16.50 Hz · 0.1033 px RMS</td>
        <td>33.23 Hz (2X) · 0.0768 px RMS</td>
        <td><span class="badge badge-pass">VALID</span></td>
      </tr>
      <tr>
        <td><strong>2000 RPM Resonance</strong><br/><code>2000rpm-Unb1.avi</code></td>
        <td>33.33 Hz</td>
        <td>33.33 Hz · 0.1292 px RMS</td>
        <td>33.38 Hz · 0.2652 px RMS</td>
        <td><span class="badge badge-contam">CONTAMINATED</span></td>
      </tr>
    </tbody>
  </table>
  <p style="font-size: 7.9pt; color: #475569; margin-top: -4px;">
    <strong>Audit Note (Kang, W. et al., <em>J. Sound Vib.</em> 2025):</strong> Evaluated at identical ROIs Target C <code>[850,460,64,64]</code> &amp; bedplate Anchor <code>[600,560,64,64]</code> (<code>--fps 500</code>). At 2000 RPM, structural resonance couples into the shared steel bedplate near 33.3 Hz (&ge;10 dB anchor prominence), so both axes honestly trigger <code>CONTAMINATED</code> and raw Y-RMS amplitude is not claimed as isolated unbalance amplification.
  </p>

  <div class="grid-2" style="margin-bottom: 6px;">
    <div class="card card-cyan">
      <div class="card-title">Automated System &amp; E2E Suites</div>
      <ul>
        <li><strong>Pytest Cleaned Suite:</strong> <strong>137 / 137 passing</strong> (100% pass rate across core math, monitoring, API, SQLite/NPZ storage).</li>
        <li><strong>Live Backend E2E (<code>test_live_e2e.py</code>):</strong> 4/4 workflows passed including live recalibration &amp; <code>Review</code> trigger (Z=22.54).</li>
        <li><strong>Playwright Chromium E2E:</strong> Textured <code>getUserMedia</code> achieved <strong>60.8 Hz</strong>, <strong>0</strong> drops, <strong>8.51 Hz</strong> peak; 0 page/console/HTTP-500 errors.</li>
      </ul>
    </div>
    <div class="card card-emerald">
      <div class="card-title">Real Physical Hardware Test (MacBook FaceTime HD)</div>
      <ul>
        <li><strong>Physical 4.00 Hz Optical Lock:</strong> Tracked mobile <code>/target</code> at <strong>30.3 Hz</strong>, <strong>0 drops</strong>, <strong>4.00 Hz VALID</strong> (<strong>38.3 dB</strong>, <code>TGT/ANC CORR 0.99/1.00</code>).</li>
        <li><strong>Temporal Stability:</strong> Verified <code>TIMING STATUS: STABLE</code> (<strong>2.04%</strong> jitter in 4.00 Hz run; <strong>2.98%</strong> across 1,014 frames / 33.73 s).</li>
        <li><strong>Calibration Bench:</strong> Dark-ground <code>/target</code> verified cleanly on mobile &amp; desktop theater mode (<code>844&times;390</code> iOS fallback).</li>
      </ul>
    </div>
  </div>

  {fig6_html}
</section>

<!-- ====================================================================== -->
<!-- PAGE 6: 05 / SCIENTIFIC LIMITATIONS, ROADMAP & REPRODUCIBILITY         -->
<!-- ====================================================================== -->
<section class="page">
  <div class="sec-eyebrow">05 / Scientific Boundaries, Roadmap &amp; Reproducibility</div>

  <h2 class="sub-head" style="margin-top: 2px;">Sampling Rate &amp; Nyquist Physical Feasibility Matrix (<code>analysis.py</code> Default Upper Cutoff: 0.90&times;<em>f</em><sub>Nyq</sub>)</h2>
  <table>
    <thead>
      <tr>
        <th style="width: 24%;">Camera / Sensor Tier</th>
        <th style="width: 9%;">FPS (<em>f</em><sub>s</sub>)</th>
        <th style="width: 11%;">Nyquist</th>
        <th style="width: 12%;">0.90&times; Cutoff</th>
        <th style="width: 14%;">Practical Margin</th>
        <th style="width: 30%;">Representative Industrial Screening Scope</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Low-Rate RTSP Substream</td>
        <td>15 FPS</td>
        <td>7.5 Hz</td>
        <td>6.75 Hz</td>
        <td>5.6 – 6.4 Hz</td>
        <td>Slow piping sway, structural frame oscillation (&lt;380 RPM).</td>
      </tr>
      <tr>
        <td>PAL Industrial CCTV</td>
        <td>25 FPS</td>
        <td>12.5 Hz</td>
        <td>11.25 Hz</td>
        <td>9.4 – 10.6 Hz</td>
        <td>Cooling tower fans, slow conveyors (&lt;640 RPM).</td>
      </tr>
      <tr>
        <td>Standard USB / FaceTime Cam</td>
        <td>30 FPS</td>
        <td>15.0 Hz</td>
        <td>13.50 Hz</td>
        <td>11.3 – 12.8 Hz</td>
        <td>Low-speed blowers, optical test bench (&lt;750 RPM).</td>
      </tr>
      <tr>
        <td>High-Framerate USB3 Machine</td>
        <td>60 FPS</td>
        <td>30.0 Hz</td>
        <td>27.00 Hz</td>
        <td>22.5 – 25.5 Hz</td>
        <td>1X unbalance up to ~1,440 RPM (~24 Hz) safely below Nyquist.</td>
      </tr>
      <tr>
        <td>Industrial Global-Shutter</td>
        <td>120 FPS</td>
        <td>60.0 Hz</td>
        <td>54.00 Hz</td>
        <td>45.0 – 51.0 Hz</td>
        <td>2-pole 3000 RPM motors (50 Hz), 2X harmonics @ 1500 RPM.</td>
      </tr>
      <tr>
        <td>High-Speed Machine Vision</td>
        <td>240 FPS</td>
        <td>120.0 Hz</td>
        <td>108.0 Hz</td>
        <td>90.0 – 102.0 Hz</td>
        <td>3600 RPM (60 Hz) 1X &amp; 2X harmonics up to ~100 Hz (3000 RPM).</td>
      </tr>
      <tr>
        <td>Phantom Scientific Camera</td>
        <td>500 FPS</td>
        <td>250.0 Hz</td>
        <td>225.0 Hz</td>
        <td>187.5 – 212.5 Hz</td>
        <td>Turbomachinery (1000–3000 RPM), blade pass &amp; multi-order harmonics.</td>
      </tr>
    </tbody>
  </table>

  <div class="card card-amber" style="margin-bottom: 9px;">
    <div class="card-title">Explicit Technical Boundaries &amp; Honest Disclosures</div>
    <ul>
      <li><strong>Relative Pixel Measurements Only:</strong> All amplitudes &amp; baselines are reported strictly in pixels (<code>px</code>); ISO 10816/20816 severity grading (<code>mm/s</code>) is intentionally withheld unless calibrated via a co-planar physical fiducial scale.</li>
      <li><strong>Planar 2D Translation &amp; Anchor Assumptions:</strong> Assumes in-plane 2D translation within texture/correlation limits (<code>&sigma; &ge; 2.0</code>, <code>r &ge; 0.15</code>). Out-of-plane tilt, parallax, and common-mode base vibration degrade differential subtraction.</li>
      <li><strong>Non-Diagnostic Screening &amp; Rolling Shutter:</strong> A <code>Review</code> status signals statistical spectral divergence from healthy baseline; it does not diagnose inner-raceway faults or RUL. Standard CMOS rolling shutter distorts uniform motion above ~30 Hz.</li>
    </ul>
  </div>

  <h2 class="sub-head">Two-Stage Future Development Roadmap</h2>
  <div class="grid-2" style="margin-bottom: 9px;">
    <div class="card card-cyan">
      <div class="card-title">Stage 1 — Grand Finale Hardening (Dec 1, 2026)</div>
      <ul>
        <li>Tested hardware RTSP/IP camera ingestion adapter with reconnect logic.</li>
        <li>Adaptive reference keyframing to absorb long-duration diurnal thermal drift.</li>
        <li>Two-point interactive physical scale calibration wizard (<code>px</code> &rarr; <code>&mu;m</code>).</li>
        <li>Guarded 12 V low-voltage brushless motor rig validation (physical T4/T5 trial).</li>
      </ul>
    </div>
    <div class="card">
      <div class="card-title">Stage 2 — Post-Finals Industrial Scaling</div>
      <ul>
        <li>Multi-camera distributed worker orchestration backed by PostgreSQL storage.</li>
        <li>Affine / Enhanced Correlation Coefficient (ECC) registration for camera tilt.</li>
        <li>Kinematic asset digital twins overlaying theoretical bearing/gear orders.</li>
        <li>Domain-validated alert thresholds calibrated alongside physical triaxial IEPE sensors.</li>
      </ul>
    </div>
  </div>

  <div class="card" style="background: #F1F5F9; padding: 7px 10px; margin-bottom: 6px;">
    <div class="card-title">Reproducibility &amp; Local Execution Commands</div>
    <div class="mono" style="font-size: 7.7pt; color: #0F172A; line-height: 1.45;">
      ./scripts/dev.sh &nbsp;# Launch FastAPI (8000) + Next.js Workstation (3000)<br/>
      .venv/bin/python scripts/reset_demo_db.py &nbsp;# Seed clean 500 FPS rotor + 60 FPS 3-run baseline DB<br/>
      .venv/bin/python -m pytest tests/ -q &nbsp;# 137/137 automated verification tests<br/>
      .venv/bin/python scripts/test_live_e2e.py &amp;&amp; .venv/bin/python scripts/test_browser_ui.py
    </div>
  </div>

  <h2 class="sub-head" style="margin: 6px 0 2px 0;">Technical References</h2>
  <ol class="ref-list">
    <li>Wadhwa, N., Rubinstein, M., Durand, F., &amp; Freeman, W. T. (2013). <em>Phase-Based Video Motion Processing.</em> ACM Trans. Graph., 32(4), Art. 80.</li>
    <li>OpenCV Library (4.x/5.x). <em>Motion Analysis &amp; Object Tracking: <code>cv2.phaseCorrelate</code> (Fourier Shift Registration).</em></li>
    <li>Welch, P. D. (1967) / SciPy Signal Processing. <code>scipy.signal.welch</code> Power Spectral Density Estimation with Median Averaging.</li>
    <li>Kang, W. et al. (2025). <em>Video-based lateral vibration characteristics extraction in operational rotor systems.</em> Journal of Sound and Vibration, 608, 119047. DOI: 10.1016/j.jsv.2025.119047 / Mendeley Data DOI: 10.17632/47y7rwc2yg.1.</li>
    <li>Leys, C. et al. (2013). <em>Detecting outliers via Median &amp; Scaled Median Absolute Deviation (MAD).</em> J. Exp. Soc. Psychol., 49(4), 764–766.</li>
  </ol>
</section>

</body>
</html>
"""


async def render_pdf(video_url: str, repo_url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html_content = _build_html(video_url=video_url, repo_url=repo_url)

    footer_html = """
    <div style="width:100%; font-family:-apple-system, BlinkMacSystemFont, sans-serif; font-size:8px; color:#64748B; padding:4px 14mm 0 14mm; display:flex; justify-content:space-between; align-items:center; border-top:0.5px solid #CBD5E1;">
      <span style="letter-spacing:0.06em; font-weight:700; color:#475569;">PHASESIGHT — PRASUNEX INNOVATHON 2026 ROUND 3</span>
      <span style="font-variant-numeric:tabular-nums;">Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
    </div>
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html_content, wait_until="domcontentloaded")
        await page.pdf(
            path=str(output_path),
            format="A4",
            print_background=True,
            margin={
                "top": "13mm",
                "bottom": "15mm",
                "left": "14mm",
                "right": "14mm",
            },
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=footer_html,
        )
        await browser.close()

    size_kb = output_path.stat().st_size / 1024.0
    print(f"Generated Round 3 Submission PDF: {output_path} ({size_kb:.1f} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the PhaseSight PRASUNEX Round 3 Editorial PDF Report"
    )
    parser.add_argument(
        "--video-url",
        type=str,
        default="https://youtu.be/PENDING_UPLOAD",
        help="YouTube unlisted demonstration video URL",
    )
    parser.add_argument(
        "--repo-url",
        type=str,
        default="https://github.com/PENDING_PUSH",
        help="GitHub repository URL",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "docs" / "PhaseSight_Round3_Submission.pdf",
        help="Output PDF file path",
    )
    args = parser.parse_args()

    asyncio.run(render_pdf(args.video_url, args.repo_url, args.out.resolve()))


if __name__ == "__main__":
    main()
