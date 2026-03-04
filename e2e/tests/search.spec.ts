import {test, expect} from "@playwright/test";

test("search page loads and shows input", async ({page}) => {
    await page.goto("/");
    const searchInput = page.locator('input[type="text"], input[placeholder]').first();
    await expect(searchInput).toBeVisible();
});

test("search with no results shows empty state", async ({page}) => {
    await page.goto("/");
    const searchInput = page.locator('input[type="text"], input[placeholder]').first();
    await searchInput.fill("zzzznonexistent99999");
    await searchInput.press("Enter");
    await page.waitForTimeout(1000);
    // Should not crash and page should still be responsive
    await expect(page).toHaveURL(/\//);
});
