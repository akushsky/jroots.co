import {useState} from "react";
import {Link} from "react-router-dom";
import {Input} from "@/components/ui/input";
import {Button} from "@/components/ui/button";
import {Card, CardContent} from "@/components/ui/card";
import {forgotPassword} from "@/api/api";
import {StatusMessage} from "@/components/shared/StatusMessage";

export default function ForgotPasswordForm() {
    const [email, setEmail] = useState("");
    const [loading, setLoading] = useState(false);
    const [success, setSuccess] = useState("");
    const [error, setError] = useState("");

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!email) {
            setError("Пожалуйста, введите email");
            return;
        }

        setLoading(true);
        setError("");
        setSuccess("");
        try {
            const data = await forgotPassword(email);
            setSuccess(data.message);
        } catch {
            setSuccess("Если этот email зарегистрирован, мы отправили ссылку для сброса пароля.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="max-w-md mx-auto mt-16">
            <Card>
                <CardContent className="p-6 space-y-4">
                    <div className="text-center">
                        <Link to="/login" className="text-sm font-medium text-indigo-600 hover:underline">
                            &larr; Назад ко входу
                        </Link>
                    </div>

                    <h2 className="text-xl font-semibold text-center">Восстановление пароля</h2>
                    <p className="text-sm text-gray-600 text-center">
                        Введите email, указанный при регистрации, и мы отправим ссылку для сброса пароля.
                    </p>
                    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                        <Input
                            type="email"
                            placeholder="Email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                        />
                        {error && <StatusMessage type="error" message={error} />}
                        {success && <StatusMessage type="success" message={success} />}
                        <Button type="submit" className="w-full" disabled={loading || !!success}>
                            {loading ? "Отправка..." : "Отправить ссылку"}
                        </Button>
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
