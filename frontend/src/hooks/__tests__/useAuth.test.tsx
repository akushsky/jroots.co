import {describe, it, expect, beforeEach} from "vitest";
import {renderHook, act} from "@testing-library/react";
import type {ReactNode} from "react";
import {MemoryRouter} from "react-router-dom";
import {AuthProvider} from "@/contexts/AuthContext";
import {useAuth} from "../useAuth";

function makeJwt(payload: Record<string, unknown>): string {
    const header = btoa(JSON.stringify({alg: "HS256", typ: "JWT"}));
    const body = btoa(JSON.stringify(payload));
    return `${header}.${body}.fakesig`;
}

function wrapper({children}: {children: ReactNode}) {
    return (
        <MemoryRouter>
            <AuthProvider>{children}</AuthProvider>
        </MemoryRouter>
    );
}

beforeEach(() => {
    localStorage.clear();
});

describe("useAuth", () => {
    it("starts unauthenticated", () => {
        const {result} = renderHook(() => useAuth(), {wrapper});
        expect(result.current.isAuthenticated).toBe(false);
        expect(result.current.user).toBeNull();
    });

    it("login sets user from token", () => {
        const token = makeJwt({
            sub: "user@test.com",
            username: "user",
            is_admin: false,
            is_verified: true,
            exp: Math.floor(Date.now() / 1000) + 3600,
        });

        const {result} = renderHook(() => useAuth(), {wrapper});
        act(() => result.current.login(token));

        expect(result.current.isAuthenticated).toBe(true);
        expect(result.current.user?.email).toBe("user@test.com");
    });

    it("logout clears user", () => {
        const token = makeJwt({
            sub: "user@test.com",
            username: "user",
            is_admin: false,
            is_verified: true,
            exp: Math.floor(Date.now() / 1000) + 3600,
        });

        const {result} = renderHook(() => useAuth(), {wrapper});
        act(() => result.current.login(token));
        act(() => result.current.logout());

        expect(result.current.isAuthenticated).toBe(false);
        expect(result.current.user).toBeNull();
    });

    it("expired token results in null user", () => {
        const token = makeJwt({
            sub: "user@test.com",
            username: "user",
            is_admin: false,
            is_verified: true,
            exp: Math.floor(Date.now() / 1000) - 100,
        });

        localStorage.setItem("token", token);
        const {result} = renderHook(() => useAuth(), {wrapper});
        expect(result.current.isAuthenticated).toBe(false);
    });
});
