import { expect, test } from "@playwright/test";

/**
 * E2E 冒烟：覆盖三条关键路径（首页 / 定价 / 登录）。
 *
 * 只断言结构性渲染，不做业务写操作；定价页价格来自后端 API，
 * 这里断言至少渲染出一个 ¥ 金额，具体数值由后端定价接口单测保证。
 */

test("首页可访问并渲染品牌标题", async ({ page }) => {
  const resp = await page.goto("/", { waitUntil: "domcontentloaded" });
  expect(resp?.status()).toBe(200);
  await expect(page).toHaveTitle(/智审/);
  await expect(page.locator("h1").first()).toBeVisible();
});

test("定价页渲染套餐与价格", async ({ page }) => {
  const resp = await page.goto("/pricing", { waitUntil: "domcontentloaded" });
  expect(resp?.status()).toBe(200);
  await expect(page.getByText("专业版").first()).toBeVisible();
  await expect(page.getByText("企业版").first()).toBeVisible();
  // 价格由 /api/v1/billing/pricing 异步渲染，等待至少出现一个 ¥ 金额
  await expect(page.getByText(/¥\s?\d/).first()).toBeVisible();
});

test("登录页渲染登录表单", async ({ page }) => {
  const resp = await page.goto("/login", { waitUntil: "domcontentloaded" });
  expect(resp?.status()).toBe(200);
  await expect(page.getByRole("textbox").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /登录/ }).first()).toBeVisible();
});
