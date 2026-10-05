import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const alias = { "@": fileURLToPath(new URL("./src", import.meta.url)) };
const liveBaseUrl = process.env.LIVE_BASE_URL ?? "http://127.0.0.1:8080";

export default defineConfig({
  test: {
    projects: [
      {
        plugins: [react()],
        resolve: { alias },
        test: {
          name: "unit",
          environment: "jsdom",
          globals: true,
          include: ["src/**/*.test.{ts,tsx}"],
          exclude: ["src/**/*.live.test.{ts,tsx}"],
          setupFiles: ["src/test/setup.ts"],
        },
      },
      {
        plugins: [react()],
        resolve: { alias },
        test: {
          name: "live",
          environment: "jsdom",
          // Same-origin to the real ingress, so no CORS applies.
          environmentOptions: { jsdom: { url: liveBaseUrl } },
          globals: true,
          include: ["src/**/*.live.test.{ts,tsx}"],
          setupFiles: ["src/test/setup.ts"],
          testTimeout: 60_000,
          hookTimeout: 60_000,
        },
      },
    ],
  },
});
