import {useRef, useState} from "react";
import {Link} from "react-router-dom";
import {AxiosError} from "axios";
import HCaptcha from "@hcaptcha/react-hcaptcha";
import {Input} from "@/components/ui/input";
import {Button} from "@/components/ui/button";
import {Card, CardContent} from "@/components/ui/card";
import {userRegister} from "@/api/api";
import {StatusMessage} from "@/components/shared/StatusMessage";

export default function RegisterForm() {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [username, setUsername] = useState("");
    const [telegramUsername, setTelegramUsername] = useState("");
    const [captchaToken, setCaptchaToken] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const captchaRef = useRef<HCaptcha>(null);

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

        setLoading(true);
        try {
            const cleanTelegram = telegramUsername.startsWith("@")
                ? telegramUsername.slice(1)
                : telegramUsername;

            const data = await userRegister(username, email, password, cleanTelegram, captchaToken);
            setSuccessMessage(data.message || "Регистрация прошла успешно.");
        } catch (err) {
            const detail = err instanceof AxiosError ? err.response?.data?.detail : undefined;
            setErrorMessage(detail || "Ошибка регистрации. Попробуйте ещё раз.");
        } finally {
            setLoading(false);
        }
    };

    function isValidTelegramUsername(tgUsername: string): boolean {
        const clean = tgUsername.startsWith("@") ? tgUsername.slice(1) : tgUsername;
        return /^[a-zA-Z0-9](?:[a-zA-Z0-9_]{3,30}[a-zA-Z0-9])?$/.test(clean);
    }

    return (
        <div className="max-w-md mx-auto mt-16">
            <Card>
                <CardContent className="p-6 space-y-4">
                    <div className="text-center">
                        <Link to="/" className="text-sm font-medium text-accent hover:underline">
                            &larr; На главную
                        </Link>
                    </div>

                    <h2 className="text-xl font-semibold text-center">Регистрация</h2>
                    {successMessage && (
                        <div className="text-center space-y-3 py-4">
                            <h3 className="text-lg font-semibold text-green-600 dark:text-green-400">
                                Регистрация прошла успешно!
                            </h3>
                            <p className="text-sm font-medium text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 px-4 py-3 rounded-lg">
                                Проверьте почту и перейдите по ссылке для подтверждения аккаунта.
                            </p>
                        </div>
                    )}
                    {errorMessage && <StatusMessage type="error" message={errorMessage} />}
                    {!successMessage && (
                        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                            <Input
                                type="text"
                                placeholder="Логин"
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
                            <Button type="submit" className="w-full" disabled={loading}>
                                {loading ? "Регистрация..." : "Зарегистрироваться"}
                            </Button>
                        </form>
                    )}
                    <p className="text-center text-sm text-muted-foreground">
                        Уже есть аккаунт?{" "}
                        <Link to="/login" className="font-semibold text-accent hover:underline">
                            Войти
                        </Link>
                    </p>
                </CardContent>
            </Card>
        </div>
    );
}
