import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E 冒烟配置。
 *
 * 默认跑本地 dev（http://localhost:3000，自动拉起 pnpm dev）；
 * 指定 E2E_BASE_URL 时可直接对远端环境（如生产）跑冒烟，不启动本地服务。
 */
const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";
const isRemote = !/^https?:\/\/(localhost|127\.0\.0\.1)(:|$)/.test(baseURL);

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: true,
  retries: 1,
  reporter: [["list"]],
  use: {
    baseURL,
    navigationTimeout: 45_000,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  ...(isRemote
    ? {}
    : {
        webServer: {
          command: "pnpm dev",
          url: baseURL,
          reuseExistingServer: true,
          timeout: 120_000,
        },
      }),
});
