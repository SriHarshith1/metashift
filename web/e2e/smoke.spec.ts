import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

const fixture = (name: string) => readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8");

test.beforeEach(async ({ page }) => {
  // The pipeline writes the real files at deploy time. Tests serve hand-built ones instead.
  await page.route("**/data/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const name = path.endsWith("/index.json") ? "index.json" : `report-${path.split("/").pop()!.replace(".json", "")}.json`;
    return route.fulfill({ contentType: "application/json", body: fixture(name) });
  });
  // Icons come from Data Dragon in production. Do not hit the network in tests.
  await page.route("https://ddragon.leagueoflegends.com/**", (route) => route.fulfill({ status: 204 }));
});

test("report page shows three columns", async ({ page }) => {
  await page.goto("/#/lol/26.21");
  for (const col of ["Rise", "Stable", "Fall"]) {
    await expect(page.getByRole("heading", { name: new RegExp(col) })).toBeVisible();
  }
  await expect(page.getByRole("heading", { level: 1, name: "Patch 26.21 · vs 26.20 meta" })).toBeVisible();
});

test("phone width shows tabs", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/#/lol/26.21");
  await expect(page.getByRole("tab", { name: /rise/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /stable/i })).toBeHidden();
  await page.getByRole("tab", { name: /fall/i }).click();
  await expect(page.getByRole("heading", { name: /fall/i })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("desktop width hides the tabs", async ({ page }) => {
  await page.goto("/#/lol/26.21");
  await expect(page.getByRole("tab", { name: /rise/i })).toBeHidden();
});

test("home redirects to the first game and lists patches newest first", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/#\/lol$/);
  const rows = page.getByRole("listitem");
  await expect(rows.first()).toContainText("26.21");
  await expect(rows.first()).toContainText("9 buffs");
});

test("clicking a card name opens the entity history", async ({ page }) => {
  await page.goto("/#/lol/26.21");
  await page.getByRole("link", { name: "Kai'Sa" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Kai'Sa" })).toBeVisible();
  const rows = page.getByRole("listitem");
  await expect(rows).toHaveCount(2);
  await expect(rows.first()).toContainText("26.21");
  await expect(rows.nth(1)).toContainText("26.20");
});

test("the footer disclaimer is on every page", async ({ page }) => {
  await page.goto("/#/lol/26.21");
  await expect(page.getByRole("contentinfo")).toContainText("Metashift isn't endorsed by Riot Games");
});

test("a missing report shows the could not load message", async ({ page }) => {
  await page.route("**/data/lol/26.99.json", (route) => route.fulfill({ status: 404, body: "" }));
  await page.goto("/#/lol/26.99");
  await expect(page.getByText("could not load data/lol/26.99.json")).toBeVisible();
});

test("theme toggle switches to dark and survives a reload", async ({ page }) => {
  await page.goto("/#/lol/26.21");
  await page.getByRole("button", { name: /switch to dark theme/i }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});
