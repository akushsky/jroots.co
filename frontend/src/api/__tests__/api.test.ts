import {describe, it, expect, vi} from "vitest";
import axios from "axios";
import {apiClient, userLogin, searchObjects, userRegister, clearImageCache} from "../api";

vi.mock("axios", async () => {
    const actual = await vi.importActual<typeof import("axios")>("axios");
    const instance = {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
        interceptors: {
            request: {use: vi.fn()},
            response: {use: vi.fn()},
        },
        defaults: {headers: {common: {}}},
    };
    return {
        ...actual,
        default: {...actual.default, create: vi.fn(() => instance)},
    };
});

describe("apiClient", () => {
    it("should be created with /api baseURL", () => {
        expect(axios.create).toHaveBeenCalledWith({baseURL: "/api"});
    });
});

describe("userLogin", () => {
    it("should post form-encoded credentials", async () => {
        const mockData = {access_token: "tok", token_type: "bearer"};
        (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({data: mockData});

        const result = await userLogin("user@test.com", "pass");
        expect(apiClient.post).toHaveBeenCalledWith(
            "/login",
            expect.any(URLSearchParams),
        );
        expect(result).toEqual(mockData);
    });
});

describe("searchObjects", () => {
    it("should call GET /search with query params", async () => {
        const mockData = {items: [], total: 0};
        (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({data: mockData});

        const result = await searchObjects("test", 0, 20);
        expect(apiClient.get).toHaveBeenCalledWith(
            "/search?q=test&skip=0&limit=20",
            expect.anything(),
        );
        expect(result).toEqual(mockData);
    });
});

describe("userRegister", () => {
    it("should post registration payload", async () => {
        const mockData = {message: "ok"};
        (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({data: mockData});

        const result = await userRegister("user", "u@test.com", "pass", "tg", "cap");
        expect(apiClient.post).toHaveBeenCalledWith("/register", {
            username: "user",
            email: "u@test.com",
            password: "pass",
            telegram_username: "tg",
            captcha_token: "cap",
        });
        expect(result).toEqual(mockData);
    });
});

describe("clearImageCache", () => {
    it("should not throw when cache is empty", () => {
        expect(() => clearImageCache()).not.toThrow();
    });
});
