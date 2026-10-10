import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: process.env.SHELFOS_DEV_DIST ?? ".next",
  // one static bundle in web/out: the ShelfOS inference server hosts it next to its API
  output: "export",
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
