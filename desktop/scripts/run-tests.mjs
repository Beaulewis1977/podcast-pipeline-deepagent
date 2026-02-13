import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, "..", "..");
const testFile = resolve(repoRoot, "tests", "test_desktop_backend.ts");

const result = spawnSync(
  process.execPath,
  ["--experimental-strip-types", "--test", testFile],
  {
    cwd: repoRoot,
    stdio: "inherit",
    env: process.env,
  },
);

process.exit(result.status ?? 1);
