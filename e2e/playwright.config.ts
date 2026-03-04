import {defineConfig} from "@playwright/test";

export default defineConfig({
    testDir: "./tests",
    timeout: 30_000,
    retries: 1,
    use: {
        baseURL: process.env.BASE_URL || "http://localhost:80",
        trace: "on-first-retry",
        screenshot: "only-on-failure",
    },
    projects: [
        {name: "chromium", use: {browserName: "chromium"}},
    ],
});
