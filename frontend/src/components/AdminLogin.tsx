import {useState} from "react";
import {useNavigate} from "react-router-dom";
import {Input} from "@/components/ui/input";
import {Button} from "@/components/ui/button";
import {userLogin} from "@/api/api";
import {useAuth} from "@/hooks/useAuth";
import {StatusMessage} from "@/components/shared/StatusMessage";

export default function AdminLogin() {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();
    const {login} = useAuth();

    const handleLogin = async () => {
        setLoading(true);
        setError("");
        try {
            const data = await userLogin(email, password);
            login(data.access_token);
            navigate("/admin/dashboard");
        } catch {
            setError("Неверные учетные данные");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="max-w-sm mx-auto mt-20 space-y-4">
            <h2 className="text-xl font-bold">Вход для администратора</h2>
            <Input
                type="email"
                placeholder="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
            />
            <Input
                type="password"
                placeholder="Пароль"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
            />
            {error && <StatusMessage type="error" message={error} />}
            <Button onClick={handleLogin} disabled={loading}>
                {loading ? "Вход..." : "Войти"}
            </Button>
        </div>
    );
}
