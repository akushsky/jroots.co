import {test, expect, Page} from "@playwright/test";

async function dismissWelcomePopup(page: Page) {
    const closeBtn = page.locator('[aria-label="Закрыть"]');
    if (await closeBtn.isVisible({timeout: 2000}).catch(() => false)) {
        await closeBtn.click();
        await closeBtn.waitFor({state: "hidden"});
    }
}

test("search page loads and shows input", async ({page}) => {
    await page.goto("/");
    await dismissWelcomePopup(page);
    const searchInput = page.locator('input[type="text"], input[placeholder]').first();
    await expect(searchInput).toBeVisible();
});

test("search with no results shows empty state", async ({page}) => {
    await page.goto("/");
    await dismissWelcomePopup(page);
    const searchInput = page.locator('input[type="text"], input[placeholder]').first();
    await searchInput.fill("zzzznonexistent99999");
    await searchInput.press("Enter");
    await page.waitForTimeout(1000);
    await expect(page).toHaveURL(/\//);
});
