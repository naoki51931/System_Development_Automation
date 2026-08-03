import { expect, test } from "@playwright/test";

test("LocalAuth login and verified organization switch", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: /SystemNavigator AI/ })).toBeVisible();
  await expect(page.getByText("AIと人が、システム開発を完成までナビゲート。")).toBeVisible();
  await page.getByLabel("テストユーザー").selectOption({ label: "organization_owner (organization_owner@quality.local)" });
  await page.getByRole("button", { name: "ログイン" }).click();
  await expect(page.getByRole("heading", { name: "ダッシュボード" })).toBeVisible();

  const selector = page.getByLabel("組織切替");
  await expect(selector.locator("option")).toHaveCount(2);
  const target = await selector.locator("option", { hasText: "quality-b" }).getAttribute("value");
  expect(target).toBeTruthy();
  await selector.selectOption(target!);
  await expect(selector).toHaveValue(target!);
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("sn.organization"))).toBe(target);
});
