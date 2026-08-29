import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    serverActions: {
      // Teaching proforma accepts course material up to 50MB (spec §4.2).
      bodySizeLimit: "55mb",
    },
  },
};

export default nextConfig;
