import {test, expect} from "@playwright/test";

test("login page loads", async ({page}) => {
    await page.goto("/login");
    await expect(page.locator('input[type="email"], input[type="text"]').first()).toBeVisible();
    await expect(page.locator('input[type="password"]').first()).toBeVisible();
});

test("login with wrong credentials shows error", async ({page}) => {
    await page.goto("/login");
    await page.locator('input[type="email"], input[type="text"]').first().fill("bad@example.com");
    await page.locator('input[type="password"]').first().fill("wrongpassword");
    await page.locator('button[type="submit"], button').filter({hasText: /вход|войти|login/i}).first().click();
    await page.waitForTimeout(1500);
    // Should stay on login page or show error
    const errorOrStillOnLogin = await page.locator("text=/неверн|error|ошибк/i").count() > 0 ||
        page.url().includes("/login");
    expect(errorOrStillOnLogin).toBeTruthy();
});

test("register page loads", async ({page}) => {
    await page.goto("/signup");
    await expect(page.locator('input[type="email"], input[type="text"]').first()).toBeVisible();
});

test("admin login page loads", async ({page}) => {
    await page.goto("/admin/login");
    await expect(page.locator('input[type="email"], input[type="text"]').first()).toBeVisible();
});
