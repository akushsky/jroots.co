import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { adminLogin } from "../api/api";

export default function AdminLogin() {
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");

    const handleLogin = async () => {
        try {
            const data = await adminLogin(username, password);
            localStorage.setItem("token", data.access_token);
            window.location.href = "/admin/dashboard";
        } catch {
            setError("Invalid credentials");
        }
    };

    return (
        <div className="max-w-sm mx-auto mt-20 space-y-4">
            <h2 className="text-xl font-bold">Admin Login</h2>
            <Input
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
            />
            <Input
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
            />
            {error && <p className="text-red-500">{error}</p>}
            <Button onClick={handleLogin}>Login</Button>
        </div>
    );
}
