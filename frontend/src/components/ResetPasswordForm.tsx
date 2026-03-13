import {useState} from "react";
import {Link, useSearchParams} from "react-router-dom";
import {Input} from "@/components/ui/input";
import {Button} from "@/components/ui/button";
import {Card, CardContent} from "@/components/ui/card";
import {resetPassword} from "@/api/api";
import {StatusMessage} from "@/components/shared/StatusMessage";
import axios from "axios";

export default function ResetPasswordForm() {
    const [searchParams] = useSearchParams();
    const token = searchParams.get("token") || "";

    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [loading, setLoading] = useState(false);
    const [success, setSuccess] = useState("");
    const [error, setError] = useState("");

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!password || !confirmPassword) {
            setError("Пожалуйста, заполните все поля");
            return;
        }

        if (password !== confirmPassword) {
            setError("Пароли не совпадают");
            return;
        }

        if (password.length < 6) {
            setError("Пароль должен содержать не менее 6 символов");
            return;
        }

        setLoading(true);
        setError("");
        setSuccess("");
        try {
            const data = await resetPassword(token, password);
            setSuccess(data.message);
        } catch (err) {
            if (axios.isAxiosError(err) && err.response?.data?.detail) {
                setError(err.response.data.detail);
            } else {
                setError("Произошла ошибка при сбросе пароля");
            }
        } finally {
            setLoading(false);
        }
    };

    if (!token) {
        return (
            <div className="max-w-md mx-auto mt-16">
                <Card>
                    <CardContent className="p-6 space-y-4 text-center">
                        <StatusMessage type="error" message="Ссылка для сброса пароля недействительна." />
                        <Link to="/forgot-password" className="text-sm font-medium text-indigo-600 hover:underline">
                            Запросить новую ссылку
                        </Link>
                    </CardContent>
                </Card>
            </div>
        );
    }

    return (
        <div className="max-w-md mx-auto mt-16">
            <Card>
                <CardContent className="p-6 space-y-4">
                    <div className="text-center">
                        <Link to="/login" className="text-sm font-medium text-indigo-600 hover:underline">
                            &larr; Назад ко входу
                        </Link>
                    </div>

                    <h2 className="text-xl font-semibold text-center">Новый пароль</h2>
                    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                        <Input
                            type="password"
                            placeholder="Новый пароль"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                        />
                        <Input
                            type="password"
                            placeholder="Подтвердите пароль"
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            required
                        />
                        {error && <StatusMessage type="error" message={error} />}
                        {success && (
                            <div className="space-y-2">
                                <StatusMessage type="success" message={success} />
                                <p className="text-center text-sm">
                                    <Link to="/login" className="font-semibold text-indigo-600 hover:underline">
                                        Войти с новым паролем
                                    </Link>
                                </p>
                            </div>
                        )}
                        {!success && (
                            <Button type="submit" className="w-full" disabled={loading}>
                                {loading ? "Сохранение..." : "Сменить пароль"}
                            </Button>
                        )}
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
