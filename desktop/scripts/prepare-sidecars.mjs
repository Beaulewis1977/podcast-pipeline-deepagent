#!/usr/bin/env node
/**
 * prepare-sidecars.mjs
 *
 * Validates and renames backend/FFmpeg binaries to Tauri target-triple
 * naming conventions so that `externalBin` entries resolve correctly in
 * both `tauri dev` and bundled production builds.
 *
 * Usage:
 *   node desktop/scripts/prepare-sidecars.mjs              # prepare binaries
 *   node desktop/scripts/prepare-sidecars.mjs --check      # dry-run validation only
 *
 * Environment variables (optional overrides):
 *   BACKEND_BIN  - path to podcast-backend executable
 *   FFMPEG_BIN   - path to ffmpeg executable
 *   FFPROBE_BIN  - path to ffprobe executable
 */

import { existsSync, copyFileSync, chmodSync, mkdirSync, readdirSync } from "node:fs";
import { resolve, basename, join } from "node:path";
import { execSync } from "node:child_process";
import { platform, arch } from "node:os";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Target triple resolution
// ---------------------------------------------------------------------------

/**
 * Map Node.js os.platform()/os.arch() values to a Rust-style target triple
 * that Tauri uses to suffix sidecar binary names.
 *
 * Examples:
 *   linux  + x64   -> x86_64-unknown-linux-gnu
 *   darwin + arm64  -> aarch64-apple-darwin
 *   win32  + x64   -> x86_64-pc-windows-msvc
 */
function resolveTargetTriple() {
  // Allow explicit override via environment
  if (process.env.TAURI_TARGET_TRIPLE) {
    return process.env.TAURI_TARGET_TRIPLE;
  }

  const archMap = {
    x64: "x86_64",
    arm64: "aarch64",
    ia32: "i686",
  };

  const platformMap = {
    linux: "unknown-linux-gnu",
    darwin: "apple-darwin",
    win32: "pc-windows-msvc",
  };

  const rustArch = archMap[arch()];
  const rustPlatform = platformMap[platform()];

  if (!rustArch || !rustPlatform) {
    throw new Error(
      `Unsupported platform: ${platform()} ${arch()}. ` +
        `Set TAURI_TARGET_TRIPLE to override.`
    );
  }

  return `${rustArch}-${rustPlatform}`;
}

// ---------------------------------------------------------------------------
// Binary discovery
// ---------------------------------------------------------------------------

/** Try to find a binary on PATH using `which` (Unix) or `where` (Windows). */
function findOnPath(name) {
  try {
    const cmd = platform() === "win32" ? `where ${name}` : `which ${name}`;
    return execSync(cmd, { encoding: "utf-8" }).trim().split("\n")[0];
  } catch {
    return null;
  }
}

/**
 * Resolve a binary source path from explicit env var, then PATH lookup.
 * Returns null if not found anywhere.
 */
function resolveBinarySource(envVar, binaryName) {
  // 1. Explicit env var override
  const envPath = process.env[envVar];
  if (envPath) {
    if (existsSync(envPath)) return resolve(envPath);
    console.warn(`  WARN: ${envVar}=${envPath} does not exist, falling back to PATH`);
  }

  // 2. PATH lookup
  const pathResult = findOnPath(binaryName);
  if (pathResult && existsSync(pathResult)) return resolve(pathResult);

  return null;
}

// ---------------------------------------------------------------------------
// Sidecar definitions
// ---------------------------------------------------------------------------

const SIDECARS = [
  {
    name: "podcast-backend",
    envVar: "BACKEND_BIN",
    binaryName: platform() === "win32" ? "podcast-backend.exe" : "podcast-backend",
    required: true,
    description: "FastAPI backend service (PyInstaller binary)",
  },
  {
    name: "ffmpeg",
    envVar: "FFMPEG_BIN",
    binaryName: platform() === "win32" ? "ffmpeg.exe" : "ffmpeg",
    required: true,
    description: "FFmpeg media processing binary",
  },
  {
    name: "ffprobe",
    envVar: "FFPROBE_BIN",
    binaryName: platform() === "win32" ? "ffprobe.exe" : "ffprobe",
    required: false,
    description: "FFprobe media info binary",
  },
];

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  const checkOnly = process.argv.includes("--check");
  const targetTriple = resolveTargetTriple();
  const scriptDir = fileURLToPath(new URL(".", import.meta.url));
  const binDir = resolve(scriptDir, "..", "src-tauri", "binaries");

  console.log(`Sidecar preparation (${checkOnly ? "check" : "prepare"})`);
  console.log(`  Target triple : ${targetTriple}`);
  console.log(`  Output dir    : ${binDir}`);
  console.log("");

  if (!checkOnly) {
    mkdirSync(binDir, { recursive: true });
  }

  const results = [];
  const ext = platform() === "win32" ? ".exe" : "";

  for (const sidecar of SIDECARS) {
    const destName = `${sidecar.name}-${targetTriple}${ext}`;
    const destPath = join(binDir, destName);

    console.log(`[${sidecar.name}] ${sidecar.description}`);

    // Check if already prepared from a previous run
    if (existsSync(destPath)) {
      console.log(`  OK: ${destName} already present`);
      results.push({ ...sidecar, status: "ready", dest: destPath });
      continue;
    }

    // Try to find source binary
    const sourcePath = resolveBinarySource(sidecar.envVar, sidecar.binaryName);

    if (!sourcePath) {
      if (sidecar.required) {
        console.error(`  FAIL: Cannot find ${sidecar.binaryName}`);
        console.error(`        Set ${sidecar.envVar} or ensure it is on PATH`);
        results.push({ ...sidecar, status: "missing" });
      } else {
        console.warn(`  SKIP: ${sidecar.binaryName} not found (optional)`);
        results.push({ ...sidecar, status: "skipped" });
      }
      continue;
    }

    console.log(`  Source: ${sourcePath}`);

    if (checkOnly) {
      console.log(`  CHECK: Would copy to ${destName}`);
      results.push({ ...sidecar, status: "would-prepare", source: sourcePath });
      continue;
    }

    // Copy and set executable permissions
    copyFileSync(sourcePath, destPath);
    try {
      chmodSync(destPath, 0o755);
    } catch {
      // chmod may fail on Windows, that's fine
    }
    console.log(`  DONE: ${destName}`);
    results.push({ ...sidecar, status: "ready", dest: destPath });
  }

  console.log("");

  // Summary
  const missing = results.filter((r) => r.status === "missing");
  const ready = results.filter((r) => r.status === "ready" || r.status === "would-prepare");
  const skipped = results.filter((r) => r.status === "skipped");

  console.log(`Summary: ${ready.length} ready, ${skipped.length} skipped, ${missing.length} missing`);

  if (missing.length > 0) {
    console.error("");
    console.error("FATAL: Required sidecar binaries are missing:");
    for (const m of missing) {
      console.error(`  - ${m.name}: set ${m.envVar} or install ${m.binaryName}`);
    }
    process.exit(1);
  }

  // List all files in binaries dir for verification
  if (!checkOnly && existsSync(binDir)) {
    console.log("");
    console.log("Binaries directory contents:");
    for (const f of readdirSync(binDir)) {
      console.log(`  ${f}`);
    }
  }

  console.log("");
  console.log("Sidecar preparation complete.");
}

main();
