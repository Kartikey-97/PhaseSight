"use client";

import React, { useState, useEffect, useCallback } from "react";
import type { Asset } from "@/lib/types";
import { api } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { LiveMonitorView } from "@/components/LiveMonitorView";
import { BatchInspectView } from "@/components/BatchInspectView";
import { AssetsHistoryView } from "@/components/AssetsHistoryView";

export default function Home() {
  const [currentTab, setCurrentTab] = useState<"live" | "batch" | "assets">("live");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [activeAsset, setActiveAsset] = useState<Asset | null>(null);

  const loadAssets = useCallback(async () => {
    try {
      const data = await api.getAssets();
      setAssets(data);
      if (data.length > 0 && !activeAsset) {
        // default to first asset if none chosen
        setActiveAsset(data[0]);
      }
    } catch (err) {
      console.error("Failed to load assets:", err);
    }
  }, [activeAsset]);

  useEffect(() => {
    loadAssets();
  }, [currentTab, loadAssets]);

  return (
    <AppShell
      currentTab={currentTab}
      onTabChange={setCurrentTab}
      assets={assets}
      activeAsset={activeAsset}
      onSelectActiveAsset={setActiveAsset}
      onRefreshAssets={loadAssets}
    >
      {currentTab === "live" && (
        <LiveMonitorView activeAsset={activeAsset} />
      )}
      {currentTab === "batch" && (
        <BatchInspectView assets={assets} activeAsset={activeAsset} />
      )}
      {currentTab === "assets" && (
        <AssetsHistoryView
          assets={assets}
          activeAsset={activeAsset}
          onSelectActiveAsset={setActiveAsset}
          onRefreshAssets={loadAssets}
        />
      )}
    </AppShell>
  );
}
