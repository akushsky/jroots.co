import {useEffect, useState} from "react";
import {useNavigate, useSearchParams} from "react-router-dom";
import {Card, CardContent} from "@/components/ui/card";
import {Alert, AlertDescription, AlertTitle} from "@/components/ui/alert";
import {CheckCircle, AlertTriangle} from "lucide-react";

export default function VerifyPage() {
    const [params] = useSearchParams();
    const [status, setStatus] = useState<"success" | "error" | "loading">("loading");
    const [countdown, setCountdown] = useState(5);
    const navigate = useNavigate();

    const token = params.get("token"); // or use `email` if you're not using token-based links yet

    useEffect(() => {
        const verifyEmail = async () => {
            try {
                const res = await fetch(`/api/verify?token=${encodeURIComponent(token || "")}`);
                if (res.ok) {
                    setStatus("success");
                } else {
                    setStatus("error");
                }
            } catch (err) {
                setStatus("error");
            }
        };

        if (token) {
            verifyEmail();
        } else {
            setStatus("error");
        }
    }, [token]);

    useEffect(() => {
        if (status === "success") {
            const interval = setInterval(() => {
                setCountdown((prev) => {
                    if (prev <= 1) {
                        clearInterval(interval);
                        navigate("/");
                    }
                    return prev - 1;
                });
            }, 1000);

            return () => clearInterval(interval);
        }
    }, [status, navigate]);

    return (
        <div className="max-w-md mx-auto mt-20">
            <Card>
                <CardContent className="p-6">
                    {status === "loading" && <p>Проверка ссылки...</p>}
                    {status === "success" && (
                        <Alert variant="default" className="flex gap-2 items-start border-green-500 text-green-700">
                            <CheckCircle className="mt-1"/>
                            <div>
                                <AlertTitle>Успех!</AlertTitle>
                                <AlertDescription>
                                    Email успешно подтвержден.<br/>
                                    Перенаправление через {countdown} секунд...
                                </AlertDescription>
                            </div>
                        </Alert>
                    )}
                    {status === "error" && (
                        <Alert variant="destructive" className="flex gap-2 items-start">
                            <AlertTriangle className="mt-1"/>
                            <div>
                                <AlertTitle>Ошибка</AlertTitle>
                                <AlertDescription>Неверная или просроченная ссылка.</AlertDescription>
                            </div>
                        </Alert>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
