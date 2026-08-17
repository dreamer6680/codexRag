import type { NextConfig } from "next";
const config: NextConfig = {
  outputFileTracingRoot: process.cwd(),
  // Standalone tracing creates pnpm symlinks that require elevated Windows
  // privileges. Docker builds run on Linux and can keep the compact output.
  output: process.platform === "win32" ? undefined : "standalone",
  // pdf-inspector contains a platform-specific Rust .node binary. Keep it out
  // of the Webpack/Turbopack bundle and let the Node.js runtime require it.
  serverExternalPackages: ["@firecrawl/pdf-inspector"],
};
export default config;
