import {useState, useRef} from "react";
import {Input} from "@/components/ui/input";
import {Button} from "@/components/ui/button";
import {Card, CardContent} from "@/components/ui/card";
import HCaptcha from "@hcaptcha/react-hcaptcha";
import {userRegister} from "@/api/api.ts";
import {Link} from "react-router-dom";

export default function RegisterForm() {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [username, setUsername] = useState("");
    const [telegramUsername, setTelegramUsername] = useState("");
    const [captchaToken, setCaptchaToken] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const captchaRef = useRef<any>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        setSuccessMessage(null);
        setErrorMessage(null);

        if (!captchaToken) {
            setErrorMessage("Пожалуйста, подтвердите, что вы не робот");
            return;
        }

        if (!email || !password || !username) {
            setErrorMessage("Пожалуйста, заполните все поля");
            return;
        }

        if (telegramUsername && !isValidTelegramUsername(telegramUsername)) {
            setErrorMessage("Неверный формат Telegram-имени пользователя");
            return;
        }

        try {
            const cleanTelegram = telegramUsername.startsWith("@")
                ? telegramUsername.slice(1)
                : telegramUsername;

            const data = await userRegister(username, email, password, cleanTelegram, captchaToken);
            setSuccessMessage(data.message || "Регистрация прошла успешно.");
        } catch (err) {
            setErrorMessage("Ошибка регистрации. Попробуйте ещё раз.");
        }
    };

    function isValidTelegramUsername(username: string): boolean {
        const clean = username.startsWith("@") ? username.slice(1) : username;
        return /^[a-zA-Z0-9](?:[a-zA-Z0-9_]{3,30}[a-zA-Z0-9])?$/.test(clean);
    }

    return (
        <div className="max-w-md mx-auto mt-16">
            <Card>
                <CardContent className="p-6 space-y-4">
                    <h2 className="text-xl font-semibold text-center">Регистрация</h2>
                    {successMessage && (
                        <div className="bg-green-100 text-green-800 px-4 py-2 rounded text-sm">
                            {successMessage}
                        </div>
                    )}
                    {errorMessage && (
                        <div className="bg-red-100 text-red-800 px-4 py-2 rounded text-sm">
                            {errorMessage}
                        </div>
                    )}
                    {!successMessage && (
                        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                            <Input
                                type="text"
                                placeholder="Имя"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                required
                            />
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
                            <Input
                                type="text"
                                placeholder="Telegram (необязательно)"
                                value={telegramUsername}
                                onChange={(e) => setTelegramUsername(e.target.value)}
                            />
                            <HCaptcha
                                sitekey="0a40b9c4-3a0a-4438-b590-05e697d46740"
                                onVerify={(token) => setCaptchaToken(token)}
                                ref={captchaRef}
                            />
                            <Button type="submit" className="w-full">
                                Зарегистрироваться
                            </Button>
                        </form>
                    )}
                    <p className="text-center text-sm text-gray-600">
                        Уже есть аккаунт?{" "}
                        <Link to="/login" className="font-semibold text-indigo-600 hover:underline">
                            Войти
                        </Link>
                    </p>
                </CardContent>
            </Card>
        </div>
    );
}
