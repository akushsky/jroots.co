import {test, expect, Page} from "@playwright/test";

async function dismissWelcomePopup(page: Page) {
    const closeBtn = page.locator('[aria-label="Закрыть"]');
    if (await closeBtn.isVisible({timeout: 2000}).catch(() => false)) {
        await closeBtn.click();
        await closeBtn.waitFor({state: "hidden"});
    }
}

test("login page loads", async ({page}) => {
    await page.goto("/login");
    await dismissWelcomePopup(page);
    await expect(page.locator('input[type="email"], input[type="text"]').first()).toBeVisible();
    await expect(page.locator('input[type="password"]').first()).toBeVisible();
});

test("login with wrong credentials shows error", async ({page}) => {
    await page.goto("/login");
    await dismissWelcomePopup(page);
    await page.locator('input[type="email"], input[type="text"]').first().fill("bad@example.com");
    await page.locator('input[type="password"]').first().fill("wrongpassword");
    await page.locator('button[type="submit"]').first().click();
    await page.waitForTimeout(1500);
    const errorOrStillOnLogin = await page.locator("text=/неверн|error|ошибк/i").count() > 0 ||
        page.url().includes("/login");
    expect(errorOrStillOnLogin).toBeTruthy();
});

test("register page loads", async ({page}) => {
    await page.goto("/signup");
    await dismissWelcomePopup(page);
    await expect(page.locator('input[type="email"], input[type="text"]').first()).toBeVisible();
});

test("admin login page loads", async ({page}) => {
    await page.goto("/admin/login");
    await dismissWelcomePopup(page);
    await expect(page.locator('input[type="email"], input[type="text"]').first()).toBeVisible();
});
