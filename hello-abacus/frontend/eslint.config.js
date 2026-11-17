import { readdirSync } from "node:fs";

import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import importPlugin from "eslint-plugin-import";
import tseslint from "typescript-eslint";

// One zone per slice, so a slice imports only from itself. Paths are relative to
// frontend/, where `pnpm run lint` runs.
const slices = readdirSync("src/features", { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name);

export default defineConfig(
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { import: importPlugin },
    settings: { "import/resolver": { node: { extensions: [".ts", ".tsx", ".js"] } } },
    rules: {
      "import/no-restricted-paths": [
        "error",
        {
          zones: [
            ...slices.map((slice) => ({
              target: `./src/features/${slice}`,
              from: "./src/features",
              except: [`./${slice}`],
              message: "A slice never imports another slice.",
            })),
            {
              target: "./src/features",
              from: "./src/app",
              message: "Only the shell imports slices, and slices never import the shell.",
            },
            {
              target: "./src/kernel",
              from: ["./src/app", "./src/features"],
              message: "The kernel imports nothing from the app.",
            },
          ],
        },
      ],
    },
  },
);
