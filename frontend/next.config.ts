import os from "os";
import type { NextConfig } from "next";

function getLocalDevOrigins(): string[] {
  const origins = new Set<string>([
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "*.local",
    "**.local",
    "192.168.*.*",
    "172.*.*.*",
    "10.*.*.*",
    "100.*.*.*",
  ]);

  const host = os.hostname();
  if (host) {
    origins.add(host);
    origins.add(`${host}.local`);
  }

  try {
    const ifaces = os.networkInterfaces();
    for (const entries of Object.values(ifaces)) {
      if (!entries) continue;
      for (const entry of entries) {
        if (entry.family === "IPv4" && entry.address) {
          origins.add(entry.address);
        }
      }
    }
  } catch {
    // Ignore interface lookup issues
  }

  return Array.from(origins);
}

const nextConfig: NextConfig = {
  allowedDevOrigins: getLocalDevOrigins(),
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
