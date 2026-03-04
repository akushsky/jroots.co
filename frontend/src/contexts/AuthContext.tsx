import {createContext, useCallback, useEffect, useMemo, useState} from "react";
import type {ReactNode} from "react";
import {jwtDecode} from "jwt-decode";
import {useNavigate} from "react-router-dom";
import {clearImageCache} from "@/api/api";
import type {JwtPayload, User} from "@/types/auth";

interface AuthContextType {
    user: User | null;
    login: (token: string) => void;
    logout: () => void;
    isAuthenticated: boolean;
}

export const AuthContext = createContext<AuthContextType>({
    user: null,
    login: () => {},
    logout: () => {},
    isAuthenticated: false,
});

function decodeToken(token: string): User | null {
    try {
        const decoded = jwtDecode<JwtPayload>(token);
        const now = Math.floor(Date.now() / 1000);
        if (decoded.exp && decoded.exp < now) {
            localStorage.removeItem("token");
            return null;
        }
        return {
            email: decoded.sub,
            username: decoded.username,
            is_verified: decoded.is_verified,
            is_admin: decoded.is_admin,
        };
    } catch {
        localStorage.removeItem("token");
        return null;
    }
}

export function AuthProvider({children}: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(() => {
        const token = localStorage.getItem("token");
        return token ? decodeToken(token) : null;
    });

    const navigate = useNavigate();

    const login = useCallback((token: string) => {
        localStorage.setItem("token", token);
        setUser(decodeToken(token));
    }, []);

    const logout = useCallback(() => {
        localStorage.removeItem("token");
        clearImageCache();
        setUser(null);
    }, []);

    useEffect(() => {
        const interval = setInterval(() => {
            const token = localStorage.getItem("token");
            if (token) {
                const decoded = decodeToken(token);
                setUser(decoded);
                if (!decoded) {
                    navigate("/login");
                }
            }
        }, 60_000);

        return () => clearInterval(interval);
    }, [navigate]);

    const value = useMemo(
        () => ({user, login, logout, isAuthenticated: !!user}),
        [user, login, logout],
    );

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
