"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import type { Asset, HealthStatus } from "@/lib/types";
import { api } from "@/lib/api";
import {
  Activity,
  Film,
  Database,
  Plus,
  ShieldCheck,
  AlertCircle,
  HelpCircle,
  Terminal,
  Gauge,
} from "lucide-react";

interface AppShellProps {
  currentTab: "live" | "batch" | "assets";
  onTabChange: (tab: "live" | "batch" | "assets") => void;
  assets: Asset[];
  activeAsset: Asset | null;
  onSelectActiveAsset: (asset: Asset | null) => void;
  onRefreshAssets: () => void;
  children: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({
  currentTab,
  onTabChange,
  assets,
  activeAsset,
  onSelectActiveAsset,
  onRefreshAssets,
  children,
}) => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [showNewAssetModal, setShowNewAssetModal] = useState<boolean>(false);
  const [newAssetName, setNewAssetName] = useState<string>("");

  // Poll backend health every 5 seconds
  useEffect(() => {
    let cancel = false;
    const check = async () => {
      try {
        const h = await api.getHealth();
        if (!cancel) setHealth(h);
      } catch {
        if (!cancel) setHealth(null);
      }
    };
    check();
    const interval = setInterval(check, 5000);
    return () => {
      cancel = true;
      clearInterval(interval);
    };
  }, []);

  const handleCreateAsset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAssetName.trim()) return;
    try {
      const created = await api.createAsset({
        name: newAssetName.trim(),
        default_target_roi: { x: 360, y: 110, width: 160, height: 160 },
        default_anchor_roi: { x: 60, y: 100, width: 160, height: 160 },
      });
      setShowNewAssetModal(false);
      setNewAssetName("");
      onRefreshAssets();
      onSelectActiveAsset(created);
    } catch (err) {
      console.error("Failed to create asset:", err);
    }
  };

  return (
    <div className="min-h-screen bg-[#070A0F] text-slate-100 flex flex-col">
      {/* 56px Top Instrument Bar */}
      <header className="h-14 bg-[#0D121A] border-b border-[rgba(255,255,255,0.08)] px-4 flex items-center justify-between gap-3 select-none sticky top-0 z-40">
        {/* Brand & Subtitle */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-[#22D3EE]/20 border border-[#22D3EE] flex items-center justify-center shrink-0">
              <Activity className="w-3.5 h-3.5 text-[#22D3EE]" />
            </div>
            <span className="font-display font-bold text-base tracking-wider text-white whitespace-nowrap">
              PHASESIGHT
            </span>
          </div>

          <span className="hidden 2xl:inline-block h-4 w-px bg-white/10" />

          <span className="hidden 2xl:inline-block text-[10px] font-mono tracking-widest text-slate-400 uppercase whitespace-nowrap">
            NON-CONTACT OPTICAL VIBRATION SCREENING
          </span>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center gap-1 bg-[#131B26] border border-white/10 rounded-lg p-1 text-xs font-mono shrink-0">
          <button
            type="button"
            onClick={() => onTabChange("live")}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md transition whitespace-nowrap shrink-0 ${
              currentTab === "live"
                ? "bg-[#22D3EE] text-black font-semibold shadow"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Activity className="w-3.5 h-3.5 shrink-0" />
            Live Monitor
          </button>
          <button
            type="button"
            onClick={() => onTabChange("batch")}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md transition whitespace-nowrap shrink-0 ${
              currentTab === "batch"
                ? "bg-[#22D3EE] text-black font-semibold shadow"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Film className="w-3.5 h-3.5 shrink-0" />
            Batch Inspect
          </button>
          <button
            type="button"
            onClick={() => onTabChange("assets")}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md transition whitespace-nowrap shrink-0 ${
              currentTab === "assets"
                ? "bg-[#22D3EE] text-black font-semibold shadow"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Database className="w-3.5 h-3.5 shrink-0" />
            Assets & History
          </button>
          <Link
            href="/target"
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-slate-400 hover:text-[#22D3EE] hover:bg-white/5 transition whitespace-nowrap shrink-0"
            title="Open Optical Bench Test Target (for camera & tracking verification)"
          >
            <Gauge className="w-3.5 h-3.5 text-[#22D3EE] shrink-0" />
            <span className="hidden sm:inline">Optical Target</span>
          </Link>
        </nav>

        {/* Right Tools: Asset selector & Backend health */}
        <div className="flex items-center gap-2.5 shrink-0">
          {/* Active Asset Selector */}
          <div className="flex items-center gap-1.5 bg-[#131B26] border border-white/10 rounded px-2 py-1 text-xs font-mono whitespace-nowrap shrink-0">
            <span className="text-slate-400 text-[10px]">ASSET:</span>
            <select
              data-testid="select-active-asset"
              value={activeAsset?.asset_id || ""}
              onChange={(e) => {
                const found = assets.find((a) => a.asset_id === e.target.value) || null;
                onSelectActiveAsset(found);
              }}
              className="bg-transparent text-slate-200 outline-none cursor-pointer max-w-[140px] truncate"
            >
              <option value="" className="bg-[#131B26]">
                -- None --
              </option>
              {assets.map((a) => (
                <option key={a.asset_id} value={a.asset_id} className="bg-[#131B26]">
                  {a.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setShowNewAssetModal(true)}
              className="text-slate-400 hover:text-[#22D3EE] ml-0.5 shrink-0"
              title="Add New Asset"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Backend Health Dot */}
          <div
            className="flex items-center gap-2 px-2.5 py-1 bg-[#131B26] border border-white/10 rounded text-xs font-mono whitespace-nowrap shrink-0"
            title={
              health
                ? `Python ${health.python_version} · OpenCV ${health.versions.cv2} · FastAPI ${health.versions.fastapi}`
                : "Backend Offline"
            }
          >
            <span
              className={`w-2 h-2 rounded-full shrink-0 ${
                health?.status === "ok"
                  ? "bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.6)]"
                  : "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.6)]"
              }`}
            />
            <span className="text-[11px] text-slate-300 hidden sm:inline whitespace-nowrap">
              {health?.status === "ok" ? "ENGINE ONLINE" : "OFFLINE"}
            </span>
            {health?.active_session_id && (
              <span className="px-1.5 py-0.2 rounded bg-cyan-950 text-[#22D3EE] border border-cyan-800 text-[9px] font-bold shrink-0">
                BUSY
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Measurement Scope Pill */}
      <div className="w-full bg-[#0D121A]/60 border-b border-white/5 px-4 py-1 flex items-center justify-between text-[11px] font-mono text-slate-400">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-[#22D3EE]" />
          <span>UNITS: RELATIVE IMAGE PIXELS (px) · SCREENING ONLY</span>
        </div>
        <div className="hidden sm:flex items-center gap-4 text-[10px]">
          <span>METHOD: SUB-PIXEL CROSS-SPECTRAL PHASE CORRELATION</span>
          <span>ESTIMATOR: WELCH PERIODOGRAM</span>
        </div>
      </div>

      {/* Main Content Area */}
      <main className="flex-1 p-4 lg:p-6 max-w-[1600px] w-full mx-auto">
        {children}
      </main>

      {/* Quick Asset Modal */}
      {showNewAssetModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
          <form
            onSubmit={handleCreateAsset}
            className="w-full max-w-sm bg-[#0D121A] border border-white/10 rounded-lg p-5 flex flex-col gap-4 text-slate-100"
          >
            <span className="text-sm font-bold font-display">
              REGISTER NEW MACHINE ASSET
            </span>

            <div className="flex flex-col gap-1 font-mono text-xs">
              <label className="text-slate-400 text-[10px]">ASSET NAME *</label>
              <input
                type="text"
                required
                placeholder="e.g. Blower Fan B-12"
                value={newAssetName}
                onChange={(e) => setNewAssetName(e.target.value)}
                className="w-full bg-[#131B26] border border-white/10 rounded px-2.5 py-1.5 text-white"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-white/10">
              <button
                type="button"
                onClick={() => setShowNewAssetModal(false)}
                className="px-3 py-1.5 rounded font-mono text-xs text-slate-400 hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 bg-[#22D3EE] text-black font-semibold rounded font-mono text-xs hover:bg-[#22D3EE]/90"
              >
                Create
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
