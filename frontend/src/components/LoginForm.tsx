import {useState} from "react";
import {Input} from "@/components/ui/input";
import {Button} from "@/components/ui/button";
import {Card, CardContent} from "@/components/ui/card";
import {userLogin} from "@/api/api.ts";
import { Link, useNavigate } from "react-router-dom";

export default function LoginForm() {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const navigate = useNavigate();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!email || !password) {
            setError("Пожалуйста, заполните все поля");
            return;
        }

        try {
            const data = await userLogin(email, password);
            localStorage.setItem("token", data.access_token);
            navigate("/");
        } catch {
            setError("Неверные учетные данные");
        }
    };

    return (
        <div className="max-w-md mx-auto mt-16">
            <Card>
                <CardContent className="p-6 space-y-4">
                    <div className="text-center">
                        <Link to="/" className="text-sm font-medium text-indigo-600 hover:underline">
                            ← На главную
                        </Link>
                    </div>

                    <h2 className="text-xl font-semibold text-center">Вход</h2>
                    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                        <Input
                            type="email"
                            placeholder="Email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                        />
                        <Input
                            type="password"
                            placeholder="Пароль"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                        />
                        {error && (
                            <div className="bg-red-100 text-red-800 px-4 py-2 rounded text-sm">
                                {error}
                            </div>
                        )}
                        <Button type="submit" className="w-full">
                            Войти
                        </Button>
                    </form>
                    <p className="text-center text-sm text-gray-600">
                        Нет аккаунта?{" "}
                        <Link to="/signup" className="font-semibold text-indigo-600 hover:underline">
                            Зарегистрироваться
                        </Link>
                    </p>
                </CardContent>
            </Card>
        </div>
    );
}
