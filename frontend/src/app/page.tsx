"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
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
  const userClearedAssetRef = useRef<boolean>(false);
  const hasAutoSelectedRef = useRef<boolean>(false);

  const handleSelectActiveAsset = useCallback((asset: Asset | null) => {
    userClearedAssetRef.current = asset === null;
    hasAutoSelectedRef.current = true;
    setActiveAsset(asset);
  }, []);

  const loadAssets = useCallback(async () => {
    try {
      const data = await api.getAssets();
      setAssets(data);
      if (data.length > 0 && !hasAutoSelectedRef.current && !userClearedAssetRef.current) {
        hasAutoSelectedRef.current = true;
        setActiveAsset((prev) => prev ?? data[0]);
      }
    } catch (err) {
      console.error("Failed to load assets:", err);
    }
  }, []);

  useEffect(() => {
    loadAssets();
  }, [currentTab, loadAssets]);

  return (
    <AppShell
      currentTab={currentTab}
      onTabChange={setCurrentTab}
      assets={assets}
      activeAsset={activeAsset}
      onSelectActiveAsset={handleSelectActiveAsset}
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
          onSelectActiveAsset={handleSelectActiveAsset}
          onRefreshAssets={loadAssets}
        />
      )}
    </AppShell>
  );
}
